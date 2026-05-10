"""Unit tests for IngestionAgent with mocked dependencies."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.ingestion import IngestionAgent
from src.models.video import ProcessingMode, VideoMetadata, VideoSourceType


def _make_metadata(video_id: str = "abc123", duration: float = 60.0) -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        source_path="/fake/video.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=duration,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=1024 * 1024,
    )


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.max_video_size_mb = 2048
    s.max_video_duration_minutes = 15
    s.output_directory = "./output"
    return s


@pytest.fixture
def agent():
    return IngestionAgent()


class TestIngestionValidation:
    async def test_rejects_unsupported_format(self, agent, tmp_path, mock_settings):
        bad_file = tmp_path / "video.txt"
        bad_file.write_text("not a video")

        with patch("src.agents.ingestion.get_settings", return_value=mock_settings), pytest.raises(
            ValueError, match="Unsupported video format"
        ):
            await agent.process(str(bad_file), ProcessingMode.LOCAL)

    async def test_rejects_file_not_found(self, agent):
        with pytest.raises(FileNotFoundError):
            await agent.process("/nonexistent/video.mp4", ProcessingMode.LOCAL)

    async def test_rejects_oversized_file(self, agent, tmp_path, mock_settings):
        mock_settings.max_video_size_mb = 0  # 0 MB limit
        video_file = tmp_path / "big.mp4"
        video_file.write_bytes(b"x" * 1024)  # 1 KB, exceeds 0 MB limit

        with patch("src.agents.ingestion.get_settings", return_value=mock_settings), pytest.raises(
            ValueError, match="exceeds"
        ):
            await agent.process(str(video_file), ProcessingMode.LOCAL)

    async def test_rejects_url_sources(self, agent):
        with pytest.raises(ValueError, match="not supported in Phase 1"):
            await agent.process("https://youtube.com/watch?v=abc", ProcessingMode.LOCAL)


class TestIngestionSuccess:
    async def test_successful_ingestion(self, agent, tmp_path, mock_settings):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"fake video content")

        metadata = _make_metadata(duration=60.0)
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.probe_video = AsyncMock(return_value=metadata)

        mock_settings.output_directory = str(tmp_path / "output")

        with (
            patch("src.agents.ingestion.get_settings", return_value=mock_settings),
            patch("src.agents.ingestion.FFmpegService", return_value=mock_ffmpeg),
        ):
            result = await agent.process(str(video_file), ProcessingMode.LOCAL)

        assert result.video_id == "abc123"
        assert result.processing_mode == ProcessingMode.LOCAL
        assert result.metadata.duration_seconds == 60.0

    async def test_rejects_long_video(self, agent, tmp_path, mock_settings):
        video_file = tmp_path / "long.mp4"
        video_file.write_bytes(b"fake video")

        metadata = _make_metadata(duration=3600.0)  # 60 minutes
        mock_ffmpeg = MagicMock()
        mock_ffmpeg.probe_video = AsyncMock(return_value=metadata)

        with (
            patch("src.agents.ingestion.get_settings", return_value=mock_settings),
            patch("src.agents.ingestion.FFmpegService", return_value=mock_ffmpeg),
            pytest.raises(ValueError, match="duration"),
        ):
            await agent.process(str(video_file), ProcessingMode.LOCAL)
