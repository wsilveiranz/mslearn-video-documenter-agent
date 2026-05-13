"""Unit tests for VideoIndexerService with mocked HTTP client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.video import ProcessingMode, VideoMetadata, VideoSourceType
from src.services.video_indexer_service import VideoIndexerService, _parse_vi_time

# ---------------------------------------------------------------------------
# Realistic VI insights fixture used in mapping tests
# ---------------------------------------------------------------------------

SAMPLE_INSIGHTS = {
    "videos": [
        {
            "insights": {
                "transcript": [
                    {
                        "id": 1,
                        "text": "Welcome to the Azure portal demo.",
                        "confidence": 0.95,
                        "speakerId": 1,
                        "language": "en-US",
                        "instances": [{"start": "0:00:01.5", "end": "0:00:04.2"}],
                    },
                    {
                        "id": 2,
                        "text": "Let me show you how to create a resource group.",
                        "confidence": 0.92,
                        "speakerId": 1,
                        "language": "en-US",
                        "instances": [{"start": "0:00:05.0", "end": "0:00:08.3"}],
                    },
                ],
                "scenes": [
                    {"id": 1, "instances": [{"start": "0:00:00", "end": "0:00:10.0"}]},
                    {"id": 2, "instances": [{"start": "0:00:10.0", "end": "0:00:25.0"}]},
                ],
                "shots": [
                    {
                        "id": 1,
                        "keyFrames": [
                            {
                                "id": 1,
                                "instances": [
                                    {"thumbnailId": "thumb-001", "start": "0:00:02.0", "end": "0:00:02.0"}
                                ],
                            }
                        ],
                        "instances": [{"start": "0:00:00", "end": "0:00:05.5"}],
                    },
                    {
                        "id": 2,
                        "keyFrames": [
                            {
                                "id": 2,
                                "instances": [
                                    {"thumbnailId": "thumb-002", "start": "0:00:07.0", "end": "0:00:07.0"}
                                ],
                            },
                            {
                                "id": 3,
                                "instances": [
                                    {"thumbnailId": "thumb-003", "start": "0:00:12.0", "end": "0:00:12.0"}
                                ],
                            },
                        ],
                        "instances": [{"start": "0:00:05.5", "end": "0:00:15.0"}],
                    },
                ],
                "ocr": [
                    {
                        "id": 1,
                        "text": "Resource groups",
                        "confidence": 0.98,
                        "left": 100,
                        "top": 50,
                        "width": 200,
                        "height": 25,
                        "language": "en",
                        "instances": [{"start": "0:00:06.0", "end": "0:00:12.0"}],
                    }
                ],
                "brands": [
                    {
                        "id": 1,
                        "name": "Azure",
                        "referenceType": "Wiki",
                        "instances": [{"start": "0:00:01.0", "end": "0:00:03.0"}],
                    }
                ],
                "namedPeople": [],
                "namedLocations": [
                    {
                        "id": 1,
                        "name": "East US",
                        "instances": [{"start": "0:00:15.0", "end": "0:00:17.0"}],
                    }
                ],
                "speakers": [{"id": 1, "name": "Speaker 1"}],
            }
        }
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.video_indexer_account_id = "account-123"
    s.video_indexer_resource_id = (
        "/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.VideoIndexer/accounts/vi-account"
    )
    s.video_indexer_location = "eastus"
    mock_cred = MagicMock()
    mock_cred.get_token.return_value = MagicMock(token="arm_token_123")
    s.get_azure_credential.return_value = mock_cred
    return s


@pytest.fixture
def service(mock_settings):
    svc = VideoIndexerService(settings=mock_settings)
    svc._http_client = AsyncMock()
    return svc


@pytest.fixture
def sample_video_metadata():
    return VideoMetadata(
        video_id="demo-001",
        source_path="/videos/demo.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=25.0,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=1024 * 1024,
    )


# ---------------------------------------------------------------------------
# _parse_vi_time
# ---------------------------------------------------------------------------


class TestParseViTime:
    def test_seconds_with_fractional(self):
        assert _parse_vi_time("0:00:01.5") == pytest.approx(1.5)

    def test_minutes_and_seconds(self):
        assert _parse_vi_time("0:01:30") == pytest.approx(90.0)

    def test_hours_minutes_seconds_with_ms(self):
        assert _parse_vi_time("1:30:00.123") == pytest.approx(5400.123)

    def test_zero(self):
        assert _parse_vi_time("0:00:00") == pytest.approx(0.0)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Unexpected VI time format"):
            _parse_vi_time("01:30")


# ---------------------------------------------------------------------------
# get_access_token
# ---------------------------------------------------------------------------


@pytest.mark.cloud
class TestGetAccessToken:
    async def test_exchanges_arm_token_for_vi_token(self, service):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"accessToken": "vi-access-token"}
        service._http_client.post = AsyncMock(return_value=mock_resp)

        token = await service.get_access_token()

        assert token == "vi-access-token"
        service._http_client.post.assert_awaited_once()

    async def test_cached_token_not_re_fetched(self, service):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"accessToken": "vi-access-token"}
        service._http_client.post = AsyncMock(return_value=mock_resp)

        token1 = await service.get_access_token()
        token2 = await service.get_access_token()

        assert token1 == token2 == "vi-access-token"
        # HTTP exchange called only once — second call uses cache
        assert service._http_client.post.await_count == 1

    async def test_non_200_raises_runtime_error(self, service):
        mock_resp = MagicMock(status_code=401)
        mock_resp.text = "Unauthorized"
        service._http_client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(RuntimeError, match="401"):
            await service.get_access_token()


# ---------------------------------------------------------------------------
# upload_video
# ---------------------------------------------------------------------------


@pytest.mark.cloud
class TestUploadVideo:
    async def test_returns_vi_video_id(self, service):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"id": "vi-video-abc"}
        service._http_client.post = AsyncMock(return_value=mock_resp)

        with patch.object(service, "get_access_token", AsyncMock(return_value="test-token")):
            vi_id = await service.upload_video("https://storage/video.mp4?sas", "vid-001")

        assert vi_id == "vi-video-abc"
        service._http_client.post.assert_awaited_once()

    async def test_non_200_raises_runtime_error(self, service):
        mock_resp = MagicMock(status_code=500)
        mock_resp.text = "Server Error"
        service._http_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(service, "get_access_token", AsyncMock(return_value="test-token")),
            pytest.raises(RuntimeError, match="500"),
        ):
            await service.upload_video("https://storage/video.mp4?sas", "vid-001")


# ---------------------------------------------------------------------------
# wait_for_index
# ---------------------------------------------------------------------------


@pytest.mark.cloud
class TestWaitForIndex:
    async def test_returns_processed_after_poll(self, service):
        resp_processing = MagicMock(status_code=200)
        resp_processing.json.return_value = {"state": "Processing"}
        resp_done = MagicMock(status_code=200)
        resp_done.json.return_value = {"state": "Processed"}
        service._http_client.get = AsyncMock(side_effect=[resp_processing, resp_done])

        with (
            patch.object(service, "get_access_token", AsyncMock(return_value="test-token")),
            patch("src.services.video_indexer_service.asyncio.sleep", AsyncMock()),
            patch("src.services.video_indexer_service.time") as mock_time,
        ):
            mock_time.time.return_value = 0.0
            result = await service.wait_for_index("vi-123", timeout_s=600, poll_interval_s=0)

        assert result == "Processed"
        assert service._http_client.get.await_count == 2

    async def test_raises_timeout_when_deadline_exceeded(self, service):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"state": "Processing"}
        service._http_client.get = AsyncMock(return_value=resp)

        with (
            patch.object(service, "get_access_token", AsyncMock(return_value="test-token")),
            patch("src.services.video_indexer_service.asyncio.sleep", AsyncMock()),
            patch("src.services.video_indexer_service.time") as mock_time,
        ):
            # First call sets deadline=1.0, second call returns 1000.0 (past deadline)
            mock_time.time.side_effect = [0.0, 1000.0]
            with pytest.raises(TimeoutError):
                await service.wait_for_index("vi-123", timeout_s=1, poll_interval_s=0)

    async def test_raises_runtime_error_on_failed_state(self, service):
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"state": "Failed", "failureCode": "InternalServerError"}
        service._http_client.get = AsyncMock(return_value=resp)

        with (
            patch.object(service, "get_access_token", AsyncMock(return_value="test-token")),
            patch("src.services.video_indexer_service.asyncio.sleep", AsyncMock()),
            pytest.raises(RuntimeError, match="InternalServerError"),
        ):
            await service.wait_for_index("vi-123", timeout_s=600, poll_interval_s=0)


# ---------------------------------------------------------------------------
# map_to_extraction_result — critical mapping test
# ---------------------------------------------------------------------------


@pytest.mark.cloud
class TestMapToExtractionResult:
    def test_full_mapping_from_sample_insights(self, service, sample_video_metadata):
        keyframe_paths = [Path(f"/fake/kf_{i:03d}.jpg") for i in range(3)]

        result = service.map_to_extraction_result(SAMPLE_INSIGHTS, keyframe_paths, sample_video_metadata)

        assert result.processing_mode == ProcessingMode.CLOUD

        # --- Transcript ---
        assert len(result.transcript) == 2
        seg0, seg1 = result.transcript
        assert seg0.text == "Welcome to the Azure portal demo."
        assert seg0.start_seconds == pytest.approx(1.5)
        assert seg0.end_seconds == pytest.approx(4.2)
        assert seg0.speaker == "Speaker 1"
        assert seg0.confidence == pytest.approx(0.95)
        assert seg1.text == "Let me show you how to create a resource group."
        assert seg1.start_seconds == pytest.approx(5.0)

        # --- Scenes ---
        assert len(result.scenes) == 2
        scene1 = next(s for s in result.scenes if s.id == "scene_001")
        scene2 = next(s for s in result.scenes if s.id == "scene_002")
        assert scene1.start_seconds == pytest.approx(0.0)
        assert scene1.end_seconds == pytest.approx(10.0)
        assert scene2.start_seconds == pytest.approx(10.0)
        assert scene2.end_seconds == pytest.approx(25.0)

        # --- Keyframes ---
        assert len(result.keyframes) == 3
        kf0 = next(k for k in result.keyframes if k.id == "kf_000")
        kf1 = next(k for k in result.keyframes if k.id == "kf_001")
        kf2 = next(k for k in result.keyframes if k.id == "kf_002")
        assert kf0.timestamp_seconds == pytest.approx(2.0)
        assert kf1.timestamp_seconds == pytest.approx(7.0)
        assert kf2.timestamp_seconds == pytest.approx(12.0)
        assert kf0.image_path == str(keyframe_paths[0])

        # --- Scene-keyframe linking ---
        # kf_000 (t=2.0) and kf_001 (t=7.0) fall within scene_001 (0-10)
        assert "kf_000" in scene1.keyframe_ids
        assert "kf_001" in scene1.keyframe_ids
        # kf_002 (t=12.0) falls within scene_002 (10-25)
        assert "kf_002" in scene2.keyframe_ids
        # Keyframes carry back-reference to their scene
        assert kf0.scene_id == "scene_001"
        assert kf2.scene_id == "scene_002"

        # --- OCR ---
        assert len(result.ocr_entries) == 1
        ocr = result.ocr_entries[0]
        assert ocr.text == "Resource groups"
        assert ocr.timestamp_seconds == pytest.approx(6.0)
        assert ocr.confidence == pytest.approx(0.98)
        assert ocr.bounding_box is not None
        assert ocr.bounding_box.x == 100
        assert ocr.bounding_box.y == 50
        assert ocr.bounding_box.width == 200
        assert ocr.bounding_box.height == 25

        # --- Entities (brands + namedPeople + namedLocations) ---
        assert len(result.entities) == 2
        entity_names = {e.name for e in result.entities}
        assert "Azure" in entity_names
        assert "East US" in entity_names
        azure_entity = next(e for e in result.entities if e.name == "Azure")
        assert azure_entity.entity_type == "brand"
        assert azure_entity.mentions == pytest.approx([1.0])
        location_entity = next(e for e in result.entities if e.name == "East US")
        assert location_entity.entity_type == "location"

    def test_empty_insights_returns_empty_result(self, service, sample_video_metadata):
        empty_insights: dict = {"videos": [{"insights": {}}]}
        result = service.map_to_extraction_result(empty_insights, [], sample_video_metadata)

        assert result.transcript == []
        assert result.scenes == []
        assert result.keyframes == []
        assert result.ocr_entries == []
        assert result.entities == []

    def test_missing_keyframe_paths_handled_gracefully(self, service, sample_video_metadata):
        """Fewer paths than keyframes → missing ones get empty string."""
        result = service.map_to_extraction_result(SAMPLE_INSIGHTS, [], sample_video_metadata)

        # 3 keyframes in insights but 0 paths provided
        assert len(result.keyframes) == 3
        for kf in result.keyframes:
            assert kf.image_path == ""
