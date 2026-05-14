"""Extraction Agent — extracts structured data from video (transcript, keyframes, OCR, scenes)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from src.config import get_settings
from src.models.video import ExtractionResult, Keyframe, ProcessingMode, VideoMetadata
from src.services.blob_storage_service import BlobStorageService
from src.services.ffmpeg_service import FFmpegService
from src.services.scene_detection_service import SceneDetectionService
from src.services.video_indexer_service import VideoIndexerService
from src.services.whisper_service import WhisperService
from src.utils.url import validate_blob_url

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()


class ExtractionAgent:
    """Extracts transcript, keyframes, scenes, OCR, and entities from video."""

    def __init__(self, foundry_client=None) -> None:
        self._foundry_client = foundry_client

    async def process(
        self,
        video_metadata: VideoMetadata,
        processing_mode: ProcessingMode,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> ExtractionResult:
        """Extract structured content from a video.

        In cloud mode, uses Azure Video Indexer + Speech.
        In local mode, uses FFmpeg + PySceneDetect + Whisper.

        Args:
            video_metadata: Metadata from the ingestion stage.
            processing_mode: Cloud or local processing.
            on_progress: Optional async callback for progress updates.

        Returns:
            ExtractionResult with transcript, scenes, keyframes, OCR, entities.
        """
        logger.info("extraction.start", video_id=video_metadata.video_id, mode=processing_mode)

        if processing_mode == ProcessingMode.CLOUD:
            return await self._extract_cloud(video_metadata, on_progress=on_progress)
        else:
            return await self._extract_local(video_metadata)

    async def _extract_cloud(
        self,
        metadata: VideoMetadata,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> ExtractionResult:
        """Cloud extraction using Azure Video Indexer + Speech."""
        settings = get_settings()
        video_id = metadata.video_id

        work_dir = Path(settings.output_directory) / video_id
        work_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Validate blob URL and extract blob_name
        blob_name = validate_blob_url(
            str(metadata.blob_url),
            settings.blob_account_url,
            settings.blob_container_name,
        )

        blob_service: BlobStorageService | None = None
        vi_service: VideoIndexerService | None = None
        vi_video_id: str | None = None

        try:
            blob_service = BlobStorageService(settings)
            vi_service = VideoIndexerService(settings)
            # 1. Generate SAS URL for Video Indexer to access the blob
            try:
                sas_url = await blob_service.generate_sas_url(blob_name)
            except Exception as e:
                logger.error("extraction.sas_url_failed", video_id=video_id, blob_name=blob_name, error=str(e))
                raise

            # 2. Submit to Video Indexer
            video_name = Path(metadata.source_path).stem
            try:
                vi_video_id = await vi_service.upload_video(sas_url, video_id, video_name=video_name)
            except Exception as e:
                logger.error("extraction.vi_upload_failed", video_id=video_id, error=str(e))
                raise

            # 3. Poll for indexing completion
            # Scale timeout: at least configured minimum, or 3x video duration (whichever is larger)
            video_duration_s = metadata.duration_seconds if metadata.duration_seconds else 0
            dynamic_timeout = max(settings.vi_indexing_timeout_s, video_duration_s * 3)
            try:
                await vi_service.wait_for_index(
                    vi_video_id,
                    timeout_s=dynamic_timeout,
                    poll_interval_s=settings.vi_poll_interval_s,
                    on_progress=on_progress,
                )
            except Exception as e:
                logger.error("extraction.vi_indexing_failed", video_id=video_id, vi_video_id=vi_video_id, error=str(e))
                raise

            # 4. Retrieve insights
            try:
                insights = await vi_service.get_insights(vi_video_id)
            except Exception as e:
                logger.error("extraction.vi_insights_failed", video_id=video_id, vi_video_id=vi_video_id, error=str(e))
                raise

            # 5. Download keyframe thumbnails
            try:
                keyframe_paths = await vi_service.download_keyframe_thumbnails(vi_video_id, insights, frames_dir)
            except Exception as e:
                logger.error(
                    "extraction.vi_thumbnails_failed",
                    video_id=video_id,
                    vi_video_id=vi_video_id,
                    error=str(e),
                )
                raise

            # 6. Map insights to ExtractionResult
            result = vi_service.map_to_extraction_result(insights, keyframe_paths, metadata)

            # 7. GPT-4o Vision analysis on keyframes (optional)
            if self._foundry_client and result.keyframes:
                from src.services.vision_service import VisionService

                vision = VisionService()
                try:
                    result.keyframes = await vision.analyze_keyframes(result.keyframes, self._foundry_client)
                except Exception as e:
                    logger.error("extraction.vision_failed", video_id=video_id, error=str(e))

            # 8. Ensure processing mode is CLOUD
            result.processing_mode = ProcessingMode.CLOUD

            logger.info(
                "extraction.cloud_complete",
                video_id=video_id,
                transcript_segments=len(result.transcript),
                scenes=len(result.scenes),
                keyframes=len(result.keyframes),
            )
            return result

        finally:
            # Cleanup Video Indexer resource (best-effort)
            if vi_video_id is not None:
                try:
                    await vi_service.delete_video(vi_video_id)
                except Exception as e:
                    logger.warning(
                        "extraction.vi_delete_failed",
                        video_id=video_id,
                        vi_video_id=vi_video_id,
                        error=str(e),
                    )
            # Cleanup blob storage (best-effort)
            try:
                deleted = await blob_service.delete_video_blobs(video_id)
                logger.info("extraction.blob_cleanup_done", video_id=video_id, blobs_deleted=deleted)
            except Exception as e:
                logger.warning(
                    "extraction.blob_cleanup_failed",
                    video_id=video_id,
                    error=str(e),
                )
            if vi_service is not None:
                try:
                    await vi_service.close()
                except Exception as e:
                    logger.warning("extraction.vi_close_failed", video_id=video_id, error=str(e))
            if blob_service is not None:
                try:
                    await blob_service.close()
                except Exception as e:
                    logger.warning("extraction.blob_close_failed", video_id=video_id, error=str(e))

    async def _extract_local(self, metadata: VideoMetadata) -> ExtractionResult:
        """Local extraction using FFmpeg + PySceneDetect + Whisper."""
        settings = get_settings()
        video_id = metadata.video_id

        # Set up per-video working directory
        work_dir = Path(settings.output_directory) / video_id
        work_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Extract audio (if present)
        ffmpeg = FFmpegService(settings)
        audio_path = work_dir / "audio.wav"
        has_audio = metadata.has_audio
        if has_audio:
            try:
                await ffmpeg.extract_audio(metadata.source_path, audio_path)
            except Exception as e:
                logger.warning("extraction.audio_failed", video_id=video_id, error=str(e))
                has_audio = False
        else:
            logger.info("extraction.no_audio_stream", video_id=video_id)

        # Run transcription (if audio extracted) and scene detection concurrently
        whisper = WhisperService(settings.whisper_model)
        scene_detector = SceneDetectionService()

        # Build task list with stable ordering
        coros = []
        task_keys = []
        if has_audio:
            coros.append(asyncio.to_thread(whisper.transcribe, audio_path))
            task_keys.append("transcript")
        coros.append(asyncio.to_thread(scene_detector.detect_scenes, metadata.source_path))
        task_keys.append("scenes")

        results = await asyncio.gather(*coros, return_exceptions=True)
        result_map = dict(zip(task_keys, results, strict=False))

        transcript = result_map.get("transcript", [])
        scenes = result_map["scenes"]

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
