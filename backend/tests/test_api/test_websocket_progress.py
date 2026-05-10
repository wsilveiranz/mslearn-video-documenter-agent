"""Tests for WebSocket progress broadcasting in pipeline functions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.websocket import ConnectionManager
from src.models.video import ProcessingStatus, VideoJob


# ---- ConnectionManager unit tests ----

class TestConnectionManager:
    """Test the ConnectionManager.send_progress method directly.

    send_progress is fire-and-forget (schedules a background task).
    We yield to the event loop after calling it so the task completes.
    """

    @pytest.mark.asyncio
    async def test_send_progress_no_connections(self):
        """send_progress is a no-op when no client is connected."""
        mgr = ConnectionManager()
        # Should not raise even with no connections registered
        mgr.send_progress("vid123", "ingestion", 1, 6, "Starting...")
        await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_send_progress_delivers_message(self):
        """send_progress sends a JSON message to every connected WebSocket."""
        import json

        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "vid123")

        mgr.send_progress("vid123", "ingestion", 1, 6, "Starting ingestion...")
        await asyncio.sleep(0.05)

        ws.send_text.assert_awaited_once()
        payload = json.loads(ws.send_text.call_args[0][0])
        assert payload["type"] == "progress"
        assert payload["video_id"] == "vid123"
        assert payload["stage"] == "ingestion"
        assert payload["step"] == 1
        assert payload["total_steps"] == 6
        assert payload["detail"] == "Starting ingestion..."

    @pytest.mark.asyncio
    async def test_send_progress_removes_disconnected_clients(self):
        """Disconnected WebSockets are removed from the connection list."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        ws.send_text.side_effect = Exception("connection closed")
        await mgr.connect(ws, "vid123")

        # Should not raise; disconnected ws should be pruned
        mgr.send_progress("vid123", "ingestion", 1, 6, "Starting...")
        await asyncio.sleep(0.05)

        assert "vid123" not in mgr._connections

    @pytest.mark.asyncio
    async def test_send_progress_multiple_connections(self):
        """Progress is broadcast to all connections watching a video."""
        mgr = ConnectionManager()
        ws1, ws2 = AsyncMock(), AsyncMock()
        await mgr.connect(ws1, "vid123")
        await mgr.connect(ws2, "vid123")

        mgr.send_progress("vid123", "extracting", 2, 6, "Extracting...")
        await asyncio.sleep(0.05)

        ws1.send_text.assert_awaited_once()
        ws2.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_progress_wrong_video_id(self):
        """send_progress only delivers to the correct video_id."""
        mgr = ConnectionManager()
        ws = AsyncMock()
        await mgr.connect(ws, "vid-A")

        mgr.send_progress("vid-B", "ingestion", 1, 6, "Starting...")
        await asyncio.sleep(0.05)

        ws.send_text.assert_not_awaited()


# ---- _run_ingestion integration tests (manager mocked) ----

class TestRunIngestionProgress:
    """Verify _run_ingestion broadcasts the expected progress messages."""

    @pytest.fixture
    def video_job(self):
        return VideoJob(video_id="testvid", status=ProcessingStatus.QUEUED)

    @pytest.mark.asyncio
    async def test_ingestion_success_broadcasts_start_and_complete(self, video_job):
        from src.models.video import VideoMetadata, VideoSourceType

        metadata = VideoMetadata(
            video_id="ingested-id",
            source_path="/fake/video.mp4",
            source_type=VideoSourceType.LOCAL_FILE,
            duration_seconds=60.0,
            resolution_width=1920,
            resolution_height=1080,
            fps=30.0,
            file_size_bytes=1024,
        )
        mock_result = MagicMock()
        mock_result.video_id = "ingested-id"
        mock_result.metadata = metadata

        with (
            patch("src.api.routes._video_jobs", {"testvid": video_job}),
            patch("src.api.routes.manager") as mock_manager,
            patch("src.api.routes.IngestionAgent") as MockAgent,
            patch("src.api.routes.get_settings") as mock_settings,
        ):
            mock_manager.send_progress = MagicMock()
            MockAgent.return_value.process = AsyncMock(return_value=mock_result)
            mock_settings.return_value.processing_mode = "local"

            from src.api.routes import _run_ingestion
            await _run_ingestion("testvid", "/fake/video.mp4")

        calls = mock_manager.send_progress.call_args_list
        stages = [c.args[1] for c in calls]
        assert "ingestion" in stages
        assert "ingestion_complete" in stages

        # Step-based progress: ingestion starts at step 1, completes at step 1
        start_call = next(c for c in calls if c.args[1] == "ingestion")
        assert start_call.args[2] == 1  # step
        assert start_call.args[3] == 6  # total_steps

        complete_call = next(c for c in calls if c.args[1] == "ingestion_complete")
        assert complete_call.args[2] == 1  # step
        assert complete_call.args[3] == 6  # total_steps

    @pytest.mark.asyncio
    async def test_ingestion_failure_broadcasts_failed(self, video_job):
        with (
            patch("src.api.routes._video_jobs", {"testvid": video_job}),
            patch("src.api.routes.manager") as mock_manager,
            patch("src.api.routes.IngestionAgent") as MockAgent,
            patch("src.api.routes.get_settings") as mock_settings,
        ):
            mock_manager.send_progress = MagicMock()
            MockAgent.return_value.process = AsyncMock(side_effect=RuntimeError("boom"))
            mock_settings.return_value.processing_mode = "local"

            from src.api.routes import _run_ingestion
            await _run_ingestion("testvid", "/fake/video.mp4")

        calls = mock_manager.send_progress.call_args_list
        stages = [c.args[1] for c in calls]
        assert "failed" in stages
