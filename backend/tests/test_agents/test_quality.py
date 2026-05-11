"""Unit tests for QualityAssessmentAgent deterministic helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.agents.quality import QualityAssessmentAgent
from src.models.video import (
    Entity,
    ExtractionResult,
    Keyframe,
    OCREntry,
    ProcessingMode,
    Scene,
    TranscriptSegment,
    VideoMetadata,
    VideoSourceType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(
    video_id: str = "vid-001",
    duration: float = 120.0,
    has_audio: bool = True,
) -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        source_path="/fake/video.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=duration,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=1024 * 1024,
        has_audio=has_audio,
    )


def _make_extraction(
    *,
    transcript: list[TranscriptSegment] | None = None,
    scenes: list[Scene] | None = None,
    keyframes: list[Keyframe] | None = None,
    ocr_entries: list[OCREntry] | None = None,
    entities: list[Entity] | None = None,
    duration: float = 120.0,
    has_audio: bool = True,
) -> ExtractionResult:
    return ExtractionResult(
        transcript=transcript or [],
        scenes=scenes or [],
        keyframes=keyframes or [],
        ocr_entries=ocr_entries or [],
        entities=entities or [],
        video_metadata=_make_metadata(duration=duration, has_audio=has_audio),
        processing_mode=ProcessingMode.LOCAL,
    )


def _build_agent() -> QualityAssessmentAgent:
    """Instantiate a QualityAssessmentAgent with a mocked FoundryChatClient."""
    mock_client = MagicMock()
    with patch("pathlib.Path.read_text", return_value="You are a quality assessor."):
        return QualityAssessmentAgent(client=mock_client)


# ---------------------------------------------------------------------------
# TestComputeRawMetrics
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeRawMetrics:
    """Tests for QualityAssessmentAgent._compute_raw_metrics."""

    def test_populated_extraction(self):
        """All metric fields should match the known input data."""
        agent = _build_agent()

        transcript = [
            TranscriptSegment(text="Hello world", start_seconds=0.0, end_seconds=5.0),
            TranscriptSegment(text="This is a test segment", start_seconds=5.0, end_seconds=12.0),
        ]
        keyframes = [
            Keyframe(id="kf1", timestamp_seconds=2.0, image_path="/img/kf1.png", ui_description="A dialog box"),
            Keyframe(id="kf2", timestamp_seconds=8.0, image_path="/img/kf2.png", ui_description=""),
        ]
        scenes = [
            Scene(id="s1", start_seconds=0.0, end_seconds=10.0),
        ]
        ocr_entries = [
            OCREntry(text="OK", timestamp_seconds=2.0),
            OCREntry(text="Cancel", timestamp_seconds=2.0),
            OCREntry(text="Submit", timestamp_seconds=8.0),
        ]
        entities = [
            Entity(name="Azure", entity_type="product"),
        ]

        extraction = _make_extraction(
            transcript=transcript,
            keyframes=keyframes,
            scenes=scenes,
            ocr_entries=ocr_entries,
            entities=entities,
            duration=120.0,
            has_audio=True,
        )

        metrics = agent._compute_raw_metrics(extraction)

        assert metrics["transcript_segments"] == 2
        # "Hello world" = 2, "This is a test segment" = 5 → 7
        assert metrics["transcript_word_count"] == 7
        # covered = (5-0) + (12-5) = 12s out of 120s = 0.1
        assert metrics["transcript_coverage_ratio"] == 0.1
        assert metrics["scenes"] == 1
        assert metrics["keyframes"] == 2
        # Only kf1 has a non-empty ui_description
        assert metrics["keyframes_with_vision"] == 1
        assert metrics["ocr_entries"] == 3
        assert metrics["entities"] == 1
        assert metrics["video_duration_seconds"] == 120.0
        assert metrics["has_audio"] is True

    def test_empty_extraction(self):
        """Edge case: extraction with no data at all."""
        agent = _build_agent()
        extraction = _make_extraction(duration=60.0, has_audio=False)

        metrics = agent._compute_raw_metrics(extraction)

        assert metrics["transcript_segments"] == 0
        assert metrics["transcript_word_count"] == 0
        assert metrics["transcript_coverage_ratio"] == 0.0
        assert metrics["scenes"] == 0
        assert metrics["keyframes"] == 0
        assert metrics["keyframes_with_vision"] == 0
        assert metrics["ocr_entries"] == 0
        assert metrics["entities"] == 0
        assert metrics["video_duration_seconds"] == 60.0
        assert metrics["has_audio"] is False

    def test_zero_duration_video(self):
        """Edge case: video with zero duration should not cause division-by-zero."""
        agent = _build_agent()
        transcript = [
            TranscriptSegment(text="word", start_seconds=0.0, end_seconds=0.0),
        ]
        extraction = _make_extraction(transcript=transcript, duration=0.0)

        metrics = agent._compute_raw_metrics(extraction)

        assert metrics["video_duration_seconds"] == 0.0
        assert metrics["transcript_coverage_ratio"] == 0.0
        assert metrics["transcript_segments"] == 1


# ---------------------------------------------------------------------------
# TestExtractJson
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractJson:
    """Tests for QualityAssessmentAgent._extract_json."""

    def test_json_in_code_fence_with_language(self):
        agent = _build_agent()
        text = '```json\n{"key": "value"}\n```'
        result = agent._extract_json(text)
        assert result == {"key": "value"}

    def test_json_in_code_fence_without_language(self):
        agent = _build_agent()
        text = '```\n{"key": "value"}\n```'
        result = agent._extract_json(text)
        assert result == {"key": "value"}

    def test_raw_json(self):
        agent = _build_agent()
        text = '{"key": "value"}'
        result = agent._extract_json(text)
        assert result == {"key": "value"}

    def test_invalid_json_raises(self):
        agent = _build_agent()
        with pytest.raises((json.JSONDecodeError, ValueError)):
            agent._extract_json("this is not json at all")


# ---------------------------------------------------------------------------
# TestBuildReport
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildReport:
    """Tests for QualityAssessmentAgent._build_report."""

    def _sample_raw_metrics(self) -> dict:
        return {
            "transcript_segments": 5,
            "transcript_word_count": 100,
            "transcript_coverage_ratio": 0.8,
            "scenes": 3,
            "keyframes": 4,
            "keyframes_with_vision": 2,
            "ocr_entries": 10,
            "entities": 2,
            "video_duration_seconds": 120.0,
            "has_audio": True,
        }

    def test_valid_parsed_json(self):
        agent = _build_agent()
        parsed = {
            "quality_level": "rich",
            "transcript_assessment": "Excellent transcript quality.",
            "visual_assessment": "Strong visual evidence.",
            "coverage_gaps": ["No gaps detected."],
            "warnings": [],
            "recommendations": ["Consider adding alt-text."],
            "grounding_confidence": 0.95,
        }
        raw = self._sample_raw_metrics()

        report = agent._build_report(parsed, raw)

        assert report.quality_level == "rich"
        assert report.transcript_assessment == "Excellent transcript quality."
        assert report.visual_assessment == "Strong visual evidence."
        assert report.coverage_gaps == ["No gaps detected."]
        assert report.warnings == []
        assert report.recommendations == ["Consider adding alt-text."]
        assert report.grounding_confidence == 0.95
        assert report.raw_metrics == raw

    def test_invalid_quality_level_defaults_to_thin(self):
        agent = _build_agent()
        parsed = {"quality_level": "superb"}
        raw = self._sample_raw_metrics()

        report = agent._build_report(parsed, raw)

        assert report.quality_level == "thin"

    def test_grounding_confidence_clamped_above_one(self):
        agent = _build_agent()
        parsed = {"grounding_confidence": 5.0}
        raw = self._sample_raw_metrics()

        report = agent._build_report(parsed, raw)

        assert report.grounding_confidence == 1.0

    def test_grounding_confidence_clamped_below_zero(self):
        agent = _build_agent()
        parsed = {"grounding_confidence": -0.5}
        raw = self._sample_raw_metrics()

        report = agent._build_report(parsed, raw)

        assert report.grounding_confidence == 0.0

    def test_missing_optional_fields_get_defaults(self):
        agent = _build_agent()
        parsed: dict = {}
        raw = self._sample_raw_metrics()

        report = agent._build_report(parsed, raw)

        assert report.quality_level == "thin"
        assert report.transcript_assessment == "Assessment unavailable."
        assert report.visual_assessment == "Assessment unavailable."
        assert report.coverage_gaps == []
        assert report.warnings == []
        assert report.recommendations == []
        assert report.grounding_confidence == 0.3
        assert report.raw_metrics == raw


# ---------------------------------------------------------------------------
# TestFallbackReport
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFallbackReport:
    """Tests for QualityAssessmentAgent._fallback_report."""

    def test_transcript_and_vision(self):
        agent = _build_agent()
        raw = {"transcript_segments": 5, "keyframes_with_vision": 3}

        report = agent._fallback_report(raw)

        assert report.quality_level == "thin"
        assert report.grounding_confidence == 0.4

    def test_transcript_only(self):
        agent = _build_agent()
        raw = {"transcript_segments": 5, "keyframes_with_vision": 0}

        report = agent._fallback_report(raw)

        assert report.quality_level == "thin"
        assert report.grounding_confidence == 0.3

    def test_vision_only(self):
        agent = _build_agent()
        raw = {"transcript_segments": 0, "keyframes_with_vision": 2}

        report = agent._fallback_report(raw)

        assert report.quality_level == "thin"
        assert report.grounding_confidence == 0.3

    def test_neither_transcript_nor_vision(self):
        agent = _build_agent()
        raw = {"transcript_segments": 0, "keyframes_with_vision": 0}

        report = agent._fallback_report(raw)

        assert report.quality_level == "minimal"
        assert report.grounding_confidence == 0.1

    def test_fallback_warnings_present(self):
        """Fallback reports should always include a warning about manual review."""
        agent = _build_agent()
        raw = {"transcript_segments": 1, "keyframes_with_vision": 0}

        report = agent._fallback_report(raw)

        assert len(report.warnings) == 1
        assert "manual review" in report.warnings[0].lower()
        assert report.raw_metrics == raw
