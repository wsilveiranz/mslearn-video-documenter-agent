"""Unit tests for ExtractionAgent cloud path with mocked Azure services."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.extraction import ExtractionAgent
from src.models.video import (
    Entity,
    ExtractionResult,
    Keyframe,
    OCREntry,
    ProcessingMode,
    Scene,
    TranscriptSegment,
    VideoMetadata,
    VideoSourceType,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings(tmp_path):
    s = MagicMock()
    s.output_directory = str(tmp_path)
    s.blob_account_url = "https://testaccount.blob.core.windows.net"
    s.blob_container_name = "test-container"
    s.vi_indexing_timeout_s = 1200
    s.vi_poll_interval_s = 15
    return s


@pytest.fixture
def video_metadata():
    return VideoMetadata(
        video_id="test-vid-001",
        source_path="/fake/video.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=30.0,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=1024 * 1024,
        blob_url="https://testaccount.blob.core.windows.net/test-container/test-vid-001/video.mp4",
    )


@pytest.fixture
def mock_blob_service():
    svc = MagicMock()
    svc.generate_sas_url = AsyncMock(
        return_value=(
            "https://testaccount.blob.core.windows.net/test-container/test-vid-001/video.mp4?sas=token"
        )
    )
    svc.close = AsyncMock()
    return svc


@pytest.fixture
def sample_extraction_result(video_metadata):
    return ExtractionResult(
        transcript=[TranscriptSegment(text="Hello Azure", start_seconds=0.0, end_seconds=2.0)],
        scenes=[Scene(id="scene_001", start_seconds=0.0, end_seconds=30.0)],
        keyframes=[Keyframe(id="kf_000", timestamp_seconds=5.0, image_path="/fake/kf.jpg")],
        ocr_entries=[OCREntry(text="Azure Portal", timestamp_seconds=5.0)],
        entities=[Entity(name="Azure", entity_type="brand", mentions=[1.0])],
        video_metadata=video_metadata,
        processing_mode=ProcessingMode.CLOUD,
    )


@pytest.fixture
def mock_vi_service(sample_extraction_result):
    svc = MagicMock()
    svc.upload_video = AsyncMock(return_value="vi-video-123")
    svc.wait_for_index = AsyncMock(return_value="Processed")
    svc.get_insights = AsyncMock(return_value={"videos": [{"insights": {}}]})
    svc.download_keyframe_thumbnails = AsyncMock(return_value=[Path("/fake/kf_000.jpg")])
    svc.map_to_extraction_result = MagicMock(return_value=sample_extraction_result)
    svc.delete_video = AsyncMock()
    svc.close = AsyncMock()
    return svc


@pytest.fixture
def agent():
    return ExtractionAgent(foundry_client=None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCloudExtractionHappyPath:
    async def test_returns_cloud_extraction_result(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
        ):
            result = await agent.process(video_metadata, ProcessingMode.CLOUD)

        assert result.processing_mode == ProcessingMode.CLOUD
        assert len(result.transcript) == 1
        assert len(result.keyframes) == 1
        assert len(result.scenes) == 1

    async def test_sas_url_passed_to_video_indexer(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        sas_url = (
            "https://testaccount.blob.core.windows.net/test-container/test-vid-001/video.mp4?sas=token"
        )
        mock_blob_service.generate_sas_url = AsyncMock(return_value=sas_url)

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)

        call_args = mock_vi_service.upload_video.call_args
        assert call_args.args[0] == sas_url

    async def test_vi_video_deleted_in_finally(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)

        mock_vi_service.delete_video.assert_awaited_once_with("vi-video-123")
        mock_vi_service.close.assert_awaited_once()
        mock_blob_service.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCloudExtractionErrors:
    async def test_video_indexer_upload_failure_propagates(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        mock_vi_service.upload_video = AsyncMock(side_effect=RuntimeError("VI unavailable"))

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
            pytest.raises(RuntimeError, match="VI unavailable"),
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)

    async def test_services_closed_even_on_error(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        mock_vi_service.upload_video = AsyncMock(side_effect=RuntimeError("upload error"))

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),pytest.raises(RuntimeError)
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)

        mock_vi_service.close.assert_awaited_once()
        mock_blob_service.close.assert_awaited_once()

    async def test_delete_not_called_when_upload_never_succeeded(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        """vi_video_id stays None when upload_video raises — delete must not be called."""
        mock_vi_service.upload_video = AsyncMock(side_effect=RuntimeError("upload error"))

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),pytest.raises(RuntimeError)
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)

        mock_vi_service.delete_video.assert_not_awaited()

    async def test_indexing_failure_propagates(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        mock_vi_service.wait_for_index = AsyncMock(side_effect=RuntimeError("indexing failed"))

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
            pytest.raises(RuntimeError, match="indexing failed"),
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)


# ---------------------------------------------------------------------------
# No keyframes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCloudExtractionNoKeyframes:
    async def test_pipeline_continues_without_vision_analysis(
        self, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        no_kf_result = ExtractionResult(
            transcript=[TranscriptSegment(text="Hello", start_seconds=0.0, end_seconds=2.0)],
            scenes=[Scene(id="scene_001", start_seconds=0.0, end_seconds=30.0)],
            keyframes=[],
            ocr_entries=[],
            entities=[],
            video_metadata=video_metadata,
            processing_mode=ProcessingMode.CLOUD,
        )
        mock_vi_service.map_to_extraction_result = MagicMock(return_value=no_kf_result)
        mock_vi_service.download_keyframe_thumbnails = AsyncMock(return_value=[])

        # Provide a foundry client so vision *would* run if there were keyframes
        agent = ExtractionAgent(foundry_client=MagicMock())

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
        ):
            result = await agent.process(video_metadata, ProcessingMode.CLOUD)

        assert result.keyframes == []
        assert result.processing_mode == ProcessingMode.CLOUD


# ---------------------------------------------------------------------------
# Vision analysis
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCloudExtractionVision:
    async def test_vision_analysis_called_when_foundry_client_and_keyframes_present(
        self, video_metadata, mock_settings, mock_blob_service, mock_vi_service, sample_extraction_result
    ):
        analyzed_kf = Keyframe(
            id="kf_000",
            timestamp_seconds=5.0,
            image_path="/fake/kf.jpg",
            ui_description="Azure portal dashboard",
        )
        mock_vision = MagicMock()
        mock_vision.analyze_keyframes = AsyncMock(return_value=[analyzed_kf])

        agent = ExtractionAgent(foundry_client=MagicMock())

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
            patch("src.services.vision_service.VisionService", return_value=mock_vision),
        ):
            result = await agent.process(video_metadata, ProcessingMode.CLOUD)

        mock_vision.analyze_keyframes.assert_awaited_once()
        assert result.keyframes[0].ui_description == "Azure portal dashboard"

    async def test_vision_not_called_without_foundry_client(
        self, agent, video_metadata, mock_settings, mock_blob_service, mock_vi_service
    ):
        mock_vision = MagicMock()
        mock_vision.analyze_keyframes = AsyncMock()

        with (
            patch("src.agents.extraction.get_settings", return_value=mock_settings),
            patch("src.agents.extraction.BlobStorageService", return_value=mock_blob_service),
            patch("src.agents.extraction.VideoIndexerService", return_value=mock_vi_service),
            patch("src.services.vision_service.VisionService", return_value=mock_vision),
        ):
            await agent.process(video_metadata, ProcessingMode.CLOUD)

        mock_vision.analyze_keyframes.assert_not_awaited()
