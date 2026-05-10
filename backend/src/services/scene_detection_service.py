"""Scene detection service using PySceneDetect for local processing mode."""

from __future__ import annotations

from pathlib import Path

import structlog

from src.models.video import Scene

logger = structlog.get_logger()


class SceneDetectionService:
    """Detects scene boundaries in screen recording videos using PySceneDetect."""

    def __init__(
        self,
        adaptive_threshold: float = 3.0,
        min_scene_len_sec: float = 1.0,
    ) -> None:
        self._threshold = adaptive_threshold
        self._min_scene_len_sec = min_scene_len_sec

    def detect_scenes(self, video_path: str | Path) -> list[Scene]:
        """Detect scene boundaries in a video file.

        This method is synchronous (CPU-bound). Callers in async contexts should
        run it via asyncio.to_thread or a thread pool executor.

        Args:
            video_path: Path to the local video file.

        Returns:
            List of Scene models ordered by start time. If no boundaries are
            detected, returns a single scene spanning the full video duration.

        Raises:
            FileNotFoundError: If the video file does not exist.
            ImportError: If scenedetect is not installed.
        """
        try:
            from scenedetect import SceneManager, open_video
            from scenedetect.detectors import AdaptiveDetector
        except ImportError as exc:
            raise ImportError(
                "PySceneDetect is not installed. "
                'Install it with: pip install "mslearn-video-documenter[local]"'
            ) from exc

        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        logger.info(
            "scene_detection_started",
            operation="detect_scenes",
            video_path=path.name,
            adaptive_threshold=self._threshold,
            min_scene_len_sec=self._min_scene_len_sec,
        )

        video = open_video(str(path))
        fps = video.frame_rate
        min_scene_len_frames = max(1, int(self._min_scene_len_sec * fps))

        scene_manager = SceneManager()
        scene_manager.add_detector(
            AdaptiveDetector(
                adaptive_threshold=self._threshold,
                min_scene_len=min_scene_len_frames,
            )
        )
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        if not scene_list:
            duration = video.duration.get_seconds() if video.duration else 0.0
            logger.warn(
                "no_scenes_detected",
                operation="detect_scenes",
                video_path=path.name,
                fallback="single scene spanning full video",
                duration_s=duration,
            )
            return [
                Scene(
                    id="scene_000",
                    start_seconds=0.0,
                    end_seconds=duration,
                    keyframe_ids=[],
                    description="",
                )
            ]

        scenes = [
            Scene(
                id=f"scene_{i:03d}",
                start_seconds=start.get_seconds(),
                end_seconds=end.get_seconds(),
                keyframe_ids=[],
                description="",
            )
            for i, (start, end) in enumerate(scene_list)
        ]

        logger.info(
            "scene_detection_complete",
            operation="detect_scenes",
            video_path=path.name,
            scene_count=len(scenes),
        )

        return scenes

    def get_keyframe_timestamps(self, scenes: list[Scene]) -> list[float]:
        """Return the midpoint timestamp for each scene.

        These timestamps are suitable for FFmpeg frame extraction.

        Args:
            scenes: List of Scene models.

        Returns:
            List of float timestamps (seconds), one per scene.
        """
        return [(scene.start_seconds + scene.end_seconds) / 2 for scene in scenes]
