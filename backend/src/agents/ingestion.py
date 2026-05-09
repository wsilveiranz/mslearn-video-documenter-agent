"""Ingestion Agent — validates and prepares video input for processing."""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

from src.config import get_settings
from src.models.video import IngestionResult, ProcessingMode, VideoSourceType
from src.services.ffmpeg_service import FFmpegService

logger = structlog.get_logger()

_SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class IngestionAgent:
    """Validates video input and uploads to blob storage if in cloud mode."""

    async def process(self, video_source: str, processing_mode: ProcessingMode) -> IngestionResult:
        """Process a video source and prepare it for extraction.

        Args:
            video_source: File path, blob URL, or YouTube URL.
            processing_mode: Cloud or local processing.

        Returns:
            IngestionResult with video metadata and staged file path.

        Raises:
            FileNotFoundError: If the local file does not exist.
            ValueError: If the source type, format, size, or duration is invalid.
        """
        logger.info("ingestion.start", operation="ingestion", source=video_source, mode=processing_mode)

        source_type = self._detect_source_type(video_source)

        if source_type != VideoSourceType.LOCAL_FILE:
            logger.warn(
                "ingestion.unsupported_source",
                operation="ingestion",
                source_type=source_type,
                message="URL-based sources are not supported in Phase 1",
            )
            raise ValueError(
                f"Source type '{source_type}' is not supported in Phase 1. "
                "Only local file paths are accepted. URL sources (YouTube, streams, Blob) "
                "will be added in Phase 3."
            )

        video_path = Path(video_source)

        if not video_path.exists():
            logger.error("ingestion.file_not_found", operation="ingestion", path=str(video_path))
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if video_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            logger.error(
                "ingestion.unsupported_format",
                operation="ingestion",
                extension=video_path.suffix,
                supported=sorted(_SUPPORTED_EXTENSIONS),
            )
            raise ValueError(
                f"Unsupported video format '{video_path.suffix}'. "
                f"Supported formats: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
            )

        settings = get_settings()
        max_size_bytes = settings.max_video_size_mb * 1024 * 1024
        file_size_bytes = video_path.stat().st_size

        if file_size_bytes > max_size_bytes:
            logger.error(
                "ingestion.file_too_large",
                operation="ingestion",
                file_size_mb=file_size_bytes / (1024 * 1024),
                max_size_mb=settings.max_video_size_mb,
            )
            raise ValueError(
                f"Video file size ({file_size_bytes / (1024 * 1024):.1f} MB) exceeds "
                f"the limit of {settings.max_video_size_mb} MB."
            )

        logger.info("ingestion.probing", operation="ingestion", path=str(video_path.name))
        ffmpeg = FFmpegService(settings)
        metadata = await ffmpeg.probe_video(video_path)

        max_duration_seconds = settings.max_video_duration_minutes * 60
        if metadata.duration_seconds > max_duration_seconds:
            logger.error(
                "ingestion.duration_exceeded",
                operation="ingestion",
                duration_s=metadata.duration_seconds,
                max_duration_s=max_duration_seconds,
            )
            raise ValueError(
                f"Video duration ({metadata.duration_seconds / 60:.1f} min) exceeds "
                f"the limit of {settings.max_video_duration_minutes} minutes."
            )

        working_dir = Path(settings.output_directory) / metadata.video_id
        working_dir.mkdir(parents=True, exist_ok=True)
        staged_path = working_dir / video_path.name
        shutil.copy2(video_path, staged_path)

        # Update source_path to the stable staged location so downstream
        # agents read from the working directory, not the original (or temp) path.
        metadata.source_path = str(staged_path)

        logger.info(
            "ingestion.complete",
            operation="ingestion",
            video_id=metadata.video_id,
            staged_path=str(staged_path),
            duration_s=metadata.duration_seconds,
        )

        return IngestionResult(
            video_id=metadata.video_id,
            blob_url=None,
            metadata=metadata,
            processing_mode=processing_mode,
        )

    def _detect_source_type(self, source: str) -> VideoSourceType:
        """Detect the type of video source from the input string."""
        if source.startswith(("http://", "https://")):
            if "youtube.com" in source or "youtu.be" in source:
                return VideoSourceType.YOUTUBE
            if "blob.core.windows.net" in source:
                return VideoSourceType.BLOB_URL
            return VideoSourceType.STREAM
        return VideoSourceType.LOCAL_FILE
