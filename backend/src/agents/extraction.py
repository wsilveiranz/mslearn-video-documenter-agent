"""Extraction Agent — extracts structured data from video (transcript, keyframes, OCR, scenes)."""

from __future__ import annotations

import structlog

from src.models.video import ExtractionResult, ProcessingMode, VideoMetadata

logger = structlog.get_logger()


class ExtractionAgent:
    """Extracts transcript, keyframes, scenes, OCR, and entities from video."""

    async def process(self, video_metadata: VideoMetadata, processing_mode: ProcessingMode) -> ExtractionResult:
        """Extract structured content from a video.
        
        In cloud mode, uses Azure Video Indexer + Speech.
        In local mode, uses FFmpeg + PySceneDetect + Whisper.
        
        Args:
            video_metadata: Metadata from the ingestion stage.
            processing_mode: Cloud or local processing.
            
        Returns:
            ExtractionResult with transcript, scenes, keyframes, OCR, entities.
        """
        logger.info("extraction.start", video_id=video_metadata.video_id, mode=processing_mode)

        if processing_mode == ProcessingMode.CLOUD:
            return await self._extract_cloud(video_metadata)
        else:
            return await self._extract_local(video_metadata)

    async def _extract_cloud(self, metadata: VideoMetadata) -> ExtractionResult:
        """Cloud extraction using Azure Video Indexer + Speech."""
        # TODO Phase 1: Implement Azure Video Indexer integration
        # - Submit video to Video Indexer
        # - Poll for completion
        # - Retrieve insights (transcript, scenes, keyframes, OCR)
        # - Download keyframe images
        # - Analyze keyframes with GPT-4o Vision
        logger.info("extraction.cloud.stub", video_id=metadata.video_id)
        return ExtractionResult(video_metadata=metadata, processing_mode=ProcessingMode.CLOUD)

    async def _extract_local(self, metadata: VideoMetadata) -> ExtractionResult:
        """Local extraction using FFmpeg + PySceneDetect + Whisper."""
        # TODO Phase 1: Implement local extraction pipeline
        # - FFmpeg: extract audio track → .wav
        # - Whisper: transcribe audio → timestamped segments
        # - PySceneDetect: detect scene boundaries
        # - FFmpeg: extract keyframes at scene changes
        # - OpenCV/Vision: OCR on keyframes
        # - GPT-4o Vision: UI state descriptions
        logger.info("extraction.local.stub", video_id=metadata.video_id)
        return ExtractionResult(video_metadata=metadata, processing_mode=ProcessingMode.LOCAL)
