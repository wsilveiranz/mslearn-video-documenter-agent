"""Async FFmpeg wrapper service for video metadata extraction, audio extraction, and frame extraction."""

from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from pathlib import Path

import structlog

from src.config import Settings, get_settings
from src.models.video import VideoMetadata, VideoSourceType

logger = structlog.get_logger()


class FFmpegService:
    """Async wrapper around FFmpeg and ffprobe for local video processing."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        ffmpeg_bin = self._settings.ffmpeg_path
        self._ffmpeg = ffmpeg_bin
        # Derive ffprobe path from ffmpeg path (same directory, sibling binary)
        ffmpeg_path = Path(ffmpeg_bin)
        if ffmpeg_path.parent != Path("."):
            self._ffprobe = str(ffmpeg_path.parent / ffmpeg_path.name.replace("ffmpeg", "ffprobe"))
        else:
            self._ffprobe = ffmpeg_bin.replace("ffmpeg", "ffprobe")

    async def probe_video(self, video_path: str | Path) -> VideoMetadata:
        """Extract metadata from a video file using ffprobe."""
        video_path = Path(video_path)
        args = [
            self._ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        logger.info("probe_video_start", operation="probe_video", path=str(video_path.name))
        stdout, _ = await self._run_ffmpeg(args)
        data = json.loads(stdout)

        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            {},
        )
        fmt = data.get("format", {})

        duration = float(fmt.get("duration") or video_stream.get("duration", 0))
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
        file_size = int(fmt.get("size", video_path.stat().st_size))

        # Parse FPS from avg_frame_rate (e.g. "30000/1001" or "30/1")
        fps_raw = video_stream.get("avg_frame_rate", "0/1")
        try:
            num, den = fps_raw.split("/")
            fps = float(num) / float(den) if float(den) else 0.0
        except (ValueError, ZeroDivisionError):
            fps = 0.0

        video_id = uuid.uuid4().hex[:12]

        logger.info(
            "probe_video_done",
            operation="probe_video",
            video_id=video_id,
            duration_s=duration,
            resolution=f"{width}x{height}",
            fps=fps,
        )

        return VideoMetadata(
            video_id=video_id,
            source_path=str(video_path),
            source_type=VideoSourceType.LOCAL_FILE,
            duration_seconds=duration,
            resolution_width=width,
            resolution_height=height,
            fps=fps,
            file_size_bytes=file_size,
        )

    async def extract_audio(
        self,
        video_path: str | Path,
        output_path: str | Path | None = None,
    ) -> Path:
        """Extract audio track as a 16kHz mono WAV file."""
        video_path = Path(video_path)
        if output_path is None:
            output_path = video_path.with_suffix(".wav")
        output_path = Path(output_path)

        args = [
            self._ffmpeg,
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_path),
        ]

        logger.info(
            "extract_audio_start",
            operation="extract_audio",
            input=str(video_path.name),
            output=str(output_path.name),
        )
        await self._run_ffmpeg(args)
        logger.info("extract_audio_done", operation="extract_audio", output=str(output_path.name))
        return output_path

    async def extract_frames_at_scenes(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        threshold: float = 0.4,
    ) -> list[Path]:
        """Extract frames at scene changes using FFmpeg scene detection."""
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        vf = f"select=gt(scene\\,{threshold}),showinfo"
        args = [
            self._ffmpeg,
            "-y",
            "-i", str(video_path),
            "-vf", vf,
            "-vsync", "vfr",
            str(output_dir / "frame_%04d.png"),
        ]

        logger.info(
            "extract_frames_scenes_start",
            operation="extract_frames_at_scenes",
            input=str(video_path.name),
            threshold=threshold,
            output_dir=str(output_dir),
        )
        await self._run_ffmpeg(args)
        frames = sorted(output_dir.glob("frame_*.png"))
        logger.info(
            "extract_frames_scenes_done",
            operation="extract_frames_at_scenes",
            frame_count=len(frames),
        )
        return frames

    async def extract_frames_at_interval(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        interval_sec: float = 5.0,
    ) -> list[Path]:
        """Extract one frame every interval_sec seconds."""
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        args = [
            self._ffmpeg,
            "-y",
            "-i", str(video_path),
            "-vf", f"fps=1/{interval_sec}",
            str(output_dir / "frame_%04d.png"),
        ]

        logger.info(
            "extract_frames_interval_start",
            operation="extract_frames_at_interval",
            input=str(video_path.name),
            interval_sec=interval_sec,
            output_dir=str(output_dir),
        )
        await self._run_ffmpeg(args)
        frames = sorted(output_dir.glob("frame_*.png"))
        logger.info(
            "extract_frames_interval_done",
            operation="extract_frames_at_interval",
            frame_count=len(frames),
        )
        return frames

    async def _run_ffmpeg(self, args: list[str]) -> tuple[str, str]:
        """Run a subprocess command and return (stdout, stderr). Raises on non-zero exit."""
        logger.debug("ffmpeg_command", operation="run_ffmpeg", cmd=args[0], arg_count=len(args))

        result = await asyncio.to_thread(
            subprocess.run,
            args,
            capture_output=True,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        if result.returncode != 0:
            logger.error(
                "ffmpeg_failed",
                operation="run_ffmpeg",
                cmd=args[0],
                return_code=result.returncode,
                stderr=stderr[-500:],  # last 500 chars to avoid log flooding
            )
            raise RuntimeError(
                f"{args[0]} exited with code {result.returncode}. stderr: {stderr[-500:]}"
            )

        return stdout, stderr
