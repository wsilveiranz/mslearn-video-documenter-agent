"""Ingestion Agent — validates and prepares video input for processing."""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

from src.config import get_settings
from src.models.video import IngestionResult, ProcessingMode, VideoSourceType
from src.services.blob_storage_service import BlobStorageService
from src.services.ffmpeg_service import FFmpegService
from src.utils.url import validate_blob_url

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

        if source_type not in (VideoSourceType.LOCAL_FILE, VideoSourceType.BLOB_URL):
            logger.warn(
                "ingestion.unsupported_source",
                operation="ingestion",
                source_type=source_type,
            )
            raise ValueError(
                f"Source type '{source_type}' is not yet supported. "
                "Accepted sources: local file paths and Azure Blob Storage URLs. "
                "YouTube and stream URLs will be added in Phase 5."
            )

        settings = get_settings()

        if source_type == VideoSourceType.BLOB_URL:
            # Download blob to a temp location under the output directory for probing/staging
            blob_name = self._blob_name_from_url(
                video_source, settings.blob_account_url, settings.blob_container_name
            )
            filename = Path(blob_name).name
            download_dir = Path(settings.output_directory) / "_downloads"
            download_dir.mkdir(parents=True, exist_ok=True)
            download_path = download_dir / filename

            logger.info(
                "ingestion.blob_download",
                operation="ingestion",
                blob_name=blob_name,
                local_path=str(download_path.name),
            )
            blob_service = BlobStorageService(settings)
            try:
                video_path = await blob_service.download_blob(blob_name, download_path)
            except Exception as e:
                logger.error(
                    "ingestion.blob_download_failed",
                    operation="ingestion",
                    blob_name=blob_name,
                    error=str(e),
                )
                raise
            finally:
                await blob_service.close()
        else:
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
        try:
            shutil.copy2(video_path, staged_path)
        finally:
            # Clean up temp download regardless of copy success/failure
            if source_type == VideoSourceType.BLOB_URL:
                try:
                    video_path.unlink()
                    logger.info("ingestion.temp_cleaned", operation="ingestion", path=str(video_path.name))
                except OSError as e:
                    logger.warning(
                        "ingestion.temp_cleanup_failed",
                        operation="ingestion",
                        path=str(video_path.name),
                        error=str(e),
                    )

        # Update source_path to the stable staged location so downstream
        # agents read from the working directory, not the original (or temp) path.
        metadata.source_path = str(staged_path)

        if source_type == VideoSourceType.BLOB_URL:
            # Already in blob storage — use the original URL as-is
            metadata.blob_url = video_source
            logger.info(
                "ingestion.blob_url_retained",
                operation="ingestion",
                video_id=metadata.video_id,
                blob_url=video_source,
            )
        elif processing_mode == ProcessingMode.CLOUD:
            # Upload to Blob Storage in cloud mode
            blob_service = BlobStorageService(settings)
            try:
                blob_url = await blob_service.upload_video(staged_path, metadata.video_id)
                metadata.blob_url = blob_url
                logger.info("ingestion.blob_uploaded", video_id=metadata.video_id, blob_url=blob_url)
            except Exception as e:
                logger.error("ingestion.blob_upload_failed", video_id=metadata.video_id, error=str(e))
                raise
            finally:
                await blob_service.close()

        logger.info(
            "ingestion.complete",
            operation="ingestion",
            video_id=metadata.video_id,
            staged_path=str(staged_path),
            duration_s=metadata.duration_seconds,
        )

        return IngestionResult(
            video_id=metadata.video_id,
            blob_url=metadata.blob_url,
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

    def _blob_name_from_url(
        self, blob_url: str, account_url: str, container_name: str
    ) -> str:
        """Extract and validate the blob name from a full Azure Blob Storage URL.

        Given ``https://account.blob.core.windows.net/container/video_id/file.mp4``
        and container ``container``, returns ``video_id/file.mp4``.

        Raises:
            ValueError: If the URL doesn't match the expected account or container.
        """
        return validate_blob_url(blob_url, account_url, container_name)
