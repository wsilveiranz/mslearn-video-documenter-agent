"""Unit tests for FFmpegService with mocked subprocess calls."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.ffmpeg_service import FFmpegService


@pytest.fixture
def settings():
    """Create a mock Settings object."""
    s = MagicMock()
    s.ffmpeg_path = "ffmpeg"
    return s


@pytest.fixture
def service(settings):
    return FFmpegService(settings)


def _make_probe_output(duration: float = 60.0, width: int = 1920, height: int = 1080) -> str:
    return json.dumps({
        "streams": [
            {
                "codec_type": "video",
                "width": width,
                "height": height,
                "avg_frame_rate": "30/1",
                "duration": str(duration),
            }
        ],
        "format": {
            "duration": str(duration),
            "size": "10485760",
        },
    })


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run to return a controlled result."""
    with patch("src.services.ffmpeg_service.subprocess.run") as mock_run:
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = 0
        result.stdout = b""
        result.stderr = b""
        mock_run.return_value = result
        yield mock_run, result


class TestProbeVideo:
    async def test_probe_video_returns_metadata(self, service, mock_subprocess, tmp_path):
        _mock_run, result = mock_subprocess
        video_file = tmp_path / "test_video.mp4"
        video_file.write_bytes(b"x" * 1000)
        probe_output = _make_probe_output(duration=120.5, width=1280, height=720)
        result.stdout = probe_output.encode()

        meta = await service.probe_video(video_file)

        assert meta.duration_seconds == 120.5
        assert meta.resolution_width == 1280
        assert meta.resolution_height == 720
        assert meta.fps == 30.0
        assert meta.file_size_bytes == 10485760
        assert len(meta.video_id) == 12

    async def test_probe_video_bad_return_code(self, service, mock_subprocess):
        _, result = mock_subprocess
        result.returncode = 1
        result.stderr = b"ffprobe error"

        with pytest.raises(RuntimeError, match="exited with code 1"):
            await service.probe_video(Path("bad_video.mp4"))


class TestExtractAudio:
    async def test_extract_audio_returns_output_path(self, service, mock_subprocess):
        result = await service.extract_audio(Path("video.mp4"), Path("audio.wav"))

        assert result == Path("audio.wav")

    async def test_extract_audio_default_output(self, service, mock_subprocess):
        result = await service.extract_audio(Path("video.mp4"))

        assert result == Path("video.wav")

    async def test_extract_audio_failure(self, service, mock_subprocess):
        _, result = mock_subprocess
        result.returncode = 1
        result.stderr = b"audio extraction failed"

        with pytest.raises(RuntimeError):
            await service.extract_audio(Path("video.mp4"))


class TestExtractFrames:
    async def test_extract_frames_at_scenes(self, service, mock_subprocess, tmp_path):
        for i in range(3):
            (tmp_path / f"frame_{i:04d}.png").touch()

        result = await service.extract_frames_at_scenes(Path("video.mp4"), tmp_path)

        assert len(result) == 3

    async def test_extract_frames_at_interval(self, service, mock_subprocess, tmp_path):
        for i in range(5):
            (tmp_path / f"frame_{i:04d}.png").touch()

        result = await service.extract_frames_at_interval(Path("video.mp4"), tmp_path, interval_sec=2.0)

        assert len(result) == 5
