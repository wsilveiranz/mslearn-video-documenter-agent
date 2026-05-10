"""Unit tests for SceneDetectionService with mocked scenedetect."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.scene_detection_service import SceneDetectionService


@pytest.fixture
def service():
    return SceneDetectionService(adaptive_threshold=3.0, min_scene_len_sec=1.0)


class TestDetectScenes:
    def test_detect_scenes_returns_scenes(self, service):
        """Test scene detection with mocked scenedetect returning multiple scenes."""
        mock_start1 = MagicMock()
        mock_start1.get_seconds.return_value = 0.0
        mock_end1 = MagicMock()
        mock_end1.get_seconds.return_value = 10.0

        mock_start2 = MagicMock()
        mock_start2.get_seconds.return_value = 10.0
        mock_end2 = MagicMock()
        mock_end2.get_seconds.return_value = 25.0

        scene_list = [(mock_start1, mock_end1), (mock_start2, mock_end2)]

        mock_video = MagicMock()
        mock_video.frame_rate = 30.0
        mock_video.duration = MagicMock()
        mock_video.duration.get_seconds.return_value = 25.0

        mock_scene_manager = MagicMock()
        mock_scene_manager.get_scene_list.return_value = scene_list

        # Direct mock approach: patch at import level
        with patch.dict("sys.modules", {
            "scenedetect": MagicMock(),
            "scenedetect.detectors": MagicMock(),
        }):
            import scenedetect
            scenedetect.open_video = MagicMock(return_value=mock_video)
            scenedetect.SceneManager = MagicMock(return_value=mock_scene_manager)

            svc = SceneDetectionService()
            result = svc.detect_scenes(Path(__file__))  # Use an existing file

        assert len(result) == 2
        assert result[0].id == "scene_000"
        assert result[0].start_seconds == 0.0
        assert result[0].end_seconds == 10.0
        assert result[1].id == "scene_001"

    def test_fallback_to_single_scene_when_no_scenes_detected(self, service):
        """Test that a single scene is returned when no boundaries are detected."""
        mock_video = MagicMock()
        mock_video.frame_rate = 30.0
        mock_video.duration = MagicMock()
        mock_video.duration.get_seconds.return_value = 60.0

        mock_scene_manager = MagicMock()
        mock_scene_manager.get_scene_list.return_value = []

        with patch.dict("sys.modules", {
            "scenedetect": MagicMock(),
            "scenedetect.detectors": MagicMock(),
        }):
            import scenedetect
            scenedetect.open_video = MagicMock(return_value=mock_video)
            scenedetect.SceneManager = MagicMock(return_value=mock_scene_manager)

            svc = SceneDetectionService()
            result = svc.detect_scenes(Path(__file__))

        assert len(result) == 1
        assert result[0].id == "scene_000"
        assert result[0].start_seconds == 0.0
        assert result[0].end_seconds == 60.0

    def test_file_not_found(self, service):
        """Test that FileNotFoundError is raised for missing video."""
        with patch.dict("sys.modules", {
            "scenedetect": MagicMock(),
            "scenedetect.detectors": MagicMock(),
        }):
            svc = SceneDetectionService()
            with pytest.raises(FileNotFoundError):
                svc.detect_scenes(Path("/nonexistent/video.mp4"))

    def test_get_keyframe_timestamps(self, service):
        """Test midpoint calculation for keyframe timestamps."""
        from src.models.video import Scene

        scenes = [
            Scene(id="s0", start_seconds=0.0, end_seconds=10.0),
            Scene(id="s1", start_seconds=10.0, end_seconds=30.0),
        ]
        timestamps = service.get_keyframe_timestamps(scenes)
        assert timestamps == [5.0, 20.0]
