"""Extraction Agent — extracts structured data from video (transcript, keyframes, OCR, scenes)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from src.config import get_settings
from src.models.video import ExtractionResult, Keyframe, ProcessingMode, VideoMetadata
from src.services.ffmpeg_service import FFmpegService
from src.services.scene_detection_service import SceneDetectionService
from src.services.whisper_service import WhisperService

logger = structlog.get_logger()


class ExtractionAgent:
    """Extracts transcript, keyframes, scenes, OCR, and entities from video."""

    def __init__(self, foundry_client=None) -> None:
        self._foundry_client = foundry_client

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
        logger.warning(
            "extraction.cloud_not_implemented",
            msg="Cloud extraction requires Phase 3 — Azure Video Indexer integration",
        )
        return ExtractionResult(video_metadata=metadata, processing_mode=ProcessingMode.CLOUD)

    async def _extract_local(self, metadata: VideoMetadata) -> ExtractionResult:
        """Local extraction using FFmpeg + PySceneDetect + Whisper."""
        settings = get_settings()
        video_id = metadata.video_id

        # Set up per-video working directory
        work_dir = Path(settings.output_directory) / video_id
        work_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Extract audio
        ffmpeg = FFmpegService(settings)
        audio_path = work_dir / "audio.wav"
        try:
            await ffmpeg.extract_audio(metadata.source_path, audio_path)
        except Exception as e:
            logger.error("extraction.audio_failed", video_id=video_id, error=str(e))
            raise

        # Run transcription and scene detection concurrently
        whisper = WhisperService(settings.whisper_model)
        scene_detector = SceneDetectionService()

        transcript_task = asyncio.to_thread(whisper.transcribe, audio_path)
        scenes_task = asyncio.to_thread(scene_detector.detect_scenes, metadata.source_path)

        transcript, scenes = await asyncio.gather(transcript_task, scenes_task, return_exceptions=True)

        if isinstance(transcript, BaseException):
            logger.error("extraction.transcription_failed", video_id=video_id, error=str(transcript))
            transcript = []
        if isinstance(scenes, BaseException):
            logger.error("extraction.scene_detection_failed", video_id=video_id, error=str(scenes))
            scenes = []

        # Extract keyframes — prefer scene-based, fall back to interval-based
        try:
            frame_paths = await ffmpeg.extract_frames_at_scenes(metadata.source_path, frames_dir)
            if not frame_paths:
                logger.info("extraction.no_scene_frames", video_id=video_id, fallback="interval")
                frame_paths = await ffmpeg.extract_frames_at_interval(
                    metadata.source_path, frames_dir, interval_sec=5.0
                )
        except Exception as e:
            logger.error("extraction.frame_extraction_failed", video_id=video_id, error=str(e))
            raise

        # Build Keyframe models with estimated timestamps
        keyframes: list[Keyframe] = []
        total_frames = len(frame_paths)
        for i, frame_path in enumerate(frame_paths):
            timestamp = (i + 1) * metadata.duration_seconds / (total_frames + 1)
            keyframes.append(
                Keyframe(
                    id=f"kf_{i:03d}",
                    timestamp_seconds=timestamp,
                    image_path=str(frame_path),
                    scene_id=None,
                )
            )

        # Assign keyframes to scenes
        scene_list = scenes if isinstance(scenes, list) else []
        for keyframe in keyframes:
            for scene in scene_list:
                if scene.start_seconds <= keyframe.timestamp_seconds < scene.end_seconds:
                    keyframe.scene_id = scene.id
                    scene.keyframe_ids.append(keyframe.id)
                    break

        logger.info(
            "extraction.keyframes_assigned",
            video_id=video_id,
            keyframe_count=len(keyframes),
            scene_count=len(scene_list),
        )

        # Vision analysis (optional — requires Foundry client)
        if self._foundry_client and keyframes:
            from src.services.vision_service import VisionService

            vision = VisionService()
            try:
                keyframes = await vision.analyze_keyframes(keyframes, self._foundry_client)
            except Exception as e:
                logger.error("extraction.vision_failed", video_id=video_id, error=str(e))
                # Continue without vision descriptions

        logger.info(
            "extraction.complete",
            video_id=video_id,
            transcript_segments=len(transcript) if isinstance(transcript, list) else 0,
            scenes=len(scene_list),
            keyframes=len(keyframes),
        )

        return ExtractionResult(
            transcript=transcript if isinstance(transcript, list) else [],
            scenes=scene_list,
            keyframes=keyframes,
            ocr_entries=[],
            entities=[],
            video_metadata=metadata,
            processing_mode=ProcessingMode.LOCAL,
        )
