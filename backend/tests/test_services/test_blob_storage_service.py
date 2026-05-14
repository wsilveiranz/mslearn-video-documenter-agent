"""Unit tests for BlobStorageService with mocked Azure clients."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.blob_storage_service import BlobStorageService


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.blob_account_url = "https://testaccount.blob.core.windows.net"
    s.blob_container_name = "test-container"
    s.blob_retention_hours = 1
    return s


@pytest.fixture
def mock_service_client():
    client = MagicMock()
    client.close = AsyncMock()
    client.get_user_delegation_key = AsyncMock(return_value=MagicMock())
    return client


@pytest.fixture
def service(mock_settings, mock_service_client):
    with (
        patch("src.services.blob_storage_service.DefaultAzureCredential"),
        patch("src.services.blob_storage_service.BlobServiceClient", return_value=mock_service_client),
    ):
        yield BlobStorageService(settings=mock_settings)


@pytest.mark.unit
class TestUploadVideo:
    async def test_blob_name_uses_video_id_and_filename(self, service, mock_service_client, tmp_path):
        video_file = tmp_path / "demo.mp4"
        video_file.write_bytes(b"fake video content")

        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = AsyncMock()
        mock_blob_client.url = "https://testaccount.blob.core.windows.net/test-container/vid123/demo.mp4"
        mock_service_client.get_blob_client.return_value = mock_blob_client

        url = await service.upload_video(video_file, "vid123")

        mock_service_client.get_blob_client.assert_called_once_with(
            container="test-container", blob="vid123/demo.mp4"
        )
        mock_blob_client.upload_blob.assert_awaited_once()
        assert url == mock_blob_client.url

    async def test_upload_error_propagates(self, service, mock_service_client, tmp_path):
        video_file = tmp_path / "demo.mp4"
        video_file.write_bytes(b"fake video content")

        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = AsyncMock(side_effect=RuntimeError("network error"))
        mock_service_client.get_blob_client.return_value = mock_blob_client

        with pytest.raises(RuntimeError, match="network error"):
            await service.upload_video(video_file, "vid123")


@pytest.mark.unit
class TestGenerateSasUrl:
    async def test_sas_token_appended_to_url(self, service, mock_service_client):
        with patch(
            "src.services.blob_storage_service.generate_blob_sas",
            return_value="sv=2023&se=expiry&sig=abc",
        ):
            url = await service.generate_sas_url("vid123/demo.mp4")

        mock_service_client.get_user_delegation_key.assert_awaited_once()
        assert "sv=2023&se=expiry&sig=abc" in url
        assert "vid123/demo.mp4" in url

    async def test_delegation_key_error_propagates(self, service, mock_service_client):
        mock_service_client.get_user_delegation_key = AsyncMock(
            side_effect=RuntimeError("auth failed")
        )

        with pytest.raises(RuntimeError, match="auth failed"):
            await service.generate_sas_url("vid123/demo.mp4")


@pytest.mark.unit
class TestUploadKeyframe:
    async def test_path_pattern_uses_video_id_and_keyframe_id(self, service, mock_service_client):
        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = AsyncMock()
        mock_blob_client.url = (
            "https://testaccount.blob.core.windows.net/test-container/vid123/keyframes/kf_001.png"
        )
        mock_service_client.get_blob_client.return_value = mock_blob_client

        url = await service.upload_keyframe(b"\x89PNG", "vid123", "kf_001")

        mock_service_client.get_blob_client.assert_called_once_with(
            container="test-container", blob="vid123/keyframes/kf_001.png"
        )
        mock_blob_client.upload_blob.assert_awaited_once_with(b"\x89PNG", overwrite=True)
        assert url == mock_blob_client.url

    async def test_keyframe_upload_error_propagates(self, service, mock_service_client):
        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob = AsyncMock(side_effect=RuntimeError("upload failed"))
        mock_service_client.get_blob_client.return_value = mock_blob_client

        with pytest.raises(RuntimeError, match="upload failed"):
            await service.upload_keyframe(b"data", "vid123", "kf_001")


@pytest.mark.unit
class TestDownloadBlob:
    async def test_file_written_to_correct_path(self, service, mock_service_client, tmp_path):
        dest = tmp_path / "downloaded.mp4"
        stream = MagicMock()
        stream.readinto = AsyncMock()
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob = AsyncMock(return_value=stream)
        mock_service_client.get_blob_client.return_value = mock_blob_client

        result = await service.download_blob("vid123/demo.mp4", dest)

        assert result == dest
        mock_blob_client.download_blob.assert_awaited_once()
        stream.readinto.assert_awaited_once()

    async def test_download_error_propagates(self, service, mock_service_client, tmp_path):
        dest = tmp_path / "downloaded.mp4"
        mock_blob_client = MagicMock()
        mock_blob_client.download_blob = AsyncMock(side_effect=RuntimeError("download failed"))
        mock_service_client.get_blob_client.return_value = mock_blob_client

        with pytest.raises(RuntimeError, match="download failed"):
            await service.download_blob("vid123/demo.mp4", dest)


@pytest.mark.unit
class TestDeleteVideoBlobs:
    async def test_lists_and_deletes_all_blobs_under_prefix(self, service, mock_service_client):
        async def _list_blobs(name_starts_with=None):
            for name in ["vid123/video.mp4", "vid123/keyframes/kf_001.png"]:
                blob = MagicMock()
                blob.name = name
                yield blob

        mock_container_client = MagicMock()
        mock_container_client.list_blobs = _list_blobs
        mock_container_client.delete_blob = AsyncMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        count = await service.delete_video_blobs("vid123")

        assert count == 2
        assert mock_container_client.delete_blob.await_count == 2
        # Verify each blob was individually deleted
        delete_calls = [c.args[0] for c in mock_container_client.delete_blob.await_args_list]
        assert "vid123/video.mp4" in delete_calls
        assert "vid123/keyframes/kf_001.png" in delete_calls

    async def test_returns_zero_when_no_blobs(self, service, mock_service_client):
        async def _empty_list(name_starts_with=None):
            return
            yield  # make it a generator

        mock_container_client = MagicMock()
        mock_container_client.list_blobs = _empty_list
        mock_container_client.delete_blob = AsyncMock()
        mock_service_client.get_container_client.return_value = mock_container_client

        count = await service.delete_video_blobs("vid123")

        assert count == 0
        mock_container_client.delete_blob.assert_not_awaited()

    async def test_delete_error_propagates(self, service, mock_service_client):
        async def _list_one(name_starts_with=None):
            blob = MagicMock()
            blob.name = "vid123/video.mp4"
            yield blob

        mock_container_client = MagicMock()
        mock_container_client.list_blobs = _list_one
        mock_container_client.delete_blob = AsyncMock(side_effect=RuntimeError("delete failed"))
        mock_service_client.get_container_client.return_value = mock_container_client

        with pytest.raises(RuntimeError, match="delete failed"):
            await service.delete_video_blobs("vid123")
