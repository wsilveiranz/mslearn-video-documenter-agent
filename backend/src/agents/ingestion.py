"""Ingestion Agent — validates and prepares video input for processing."""

from __future__ import annotations

import structlog

from src.models.video import IngestionResult, ProcessingMode, VideoMetadata, VideoSourceType

logger = structlog.get_logger()


class IngestionAgent:
    """Validates video input and uploads to blob storage if in cloud mode."""

    async def process(self, video_source: str, processing_mode: ProcessingMode) -> IngestionResult:
        """Process a video source and prepare it for extraction.
        
        Args:
            video_source: File path, blob URL, or YouTube URL.
            processing_mode: Cloud or local processing.
            
        Returns:
            IngestionResult with video metadata and blob URL (if cloud).
        """
        logger.info("ingestion.start", source=video_source, mode=processing_mode)

        source_type = self._detect_source_type(video_source)
        
        # TODO: Implement actual video validation and upload
        # Phase 1 will add:
        # - File format validation (mp4, avi, mov, mkv, webm)
        # - File size check against max_video_size_mb
        # - Duration check against max_video_duration_minutes
        # - Azure Blob upload (cloud mode)
        # - yt-dlp download (if enabled)
        
        metadata = VideoMetadata(
            video_id="placeholder-id",
            source_path=video_source,
            source_type=source_type,
            duration_seconds=0.0,
            resolution_width=0,
            resolution_height=0,
            fps=0.0,
            file_size_bytes=0,
        )

        logger.info("ingestion.complete", video_id=metadata.video_id)

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
