"""Unit tests for WhisperService with mocked whisper model."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.whisper_service import WhisperService


@pytest.fixture
def mock_whisper():
    """Patch the whisper module."""
    mock_module = MagicMock()
    mock_model = MagicMock()
    mock_module.load_model.return_value = mock_model
    with patch.dict("sys.modules", {"whisper": mock_module}):
        yield mock_module, mock_model


@pytest.fixture
def service(mock_whisper):
    return WhisperService(model_name="base")


class TestTranscribe:
    def test_transcribe_returns_segments(self, service, mock_whisper):
        _, mock_model = mock_whisper
        mock_model.transcribe.return_value = {
            "segments": [
                {"text": "Hello world", "start": 0.0, "end": 2.5, "no_speech_prob": 0.1},
                {"text": "This is a test", "start": 2.5, "end": 5.0, "no_speech_prob": 0.05},
            ]
        }

        # Use this file as a stand-in for an existing audio path
        result = service.transcribe(Path(__file__))

        assert len(result) == 2
        assert result[0].text == "Hello world"
        assert result[0].start_seconds == 0.0
        assert result[0].end_seconds == 2.5
        assert result[0].confidence == pytest.approx(0.9)
        assert result[1].text == "This is a test"

    def test_transcribe_empty_result(self, service, mock_whisper):
        _, mock_model = mock_whisper
        mock_model.transcribe.return_value = {"segments": []}

        result = service.transcribe(Path(__file__))

        assert result == []

    def test_transcribe_skips_empty_text(self, service, mock_whisper):
        _, mock_model = mock_whisper
        mock_model.transcribe.return_value = {
            "segments": [
                {"text": "", "start": 0.0, "end": 1.0},
                {"text": "  ", "start": 1.0, "end": 2.0},
                {"text": "Valid text", "start": 2.0, "end": 3.0},
            ]
        }

        result = service.transcribe(Path(__file__))

        assert len(result) == 1
        assert result[0].text == "Valid text"

    def test_transcribe_file_not_found(self, service):
        with pytest.raises(FileNotFoundError):
            service.transcribe(Path("/nonexistent/audio.wav"))

    def test_transcribe_failure_raises_runtime_error(self, service, mock_whisper):
        _, mock_model = mock_whisper
        mock_model.transcribe.side_effect = Exception("model error")

        with pytest.raises(RuntimeError, match="Whisper transcription failed"):
            service.transcribe(Path(__file__))


class TestGetFullTranscript:
    def test_join_segments(self, service):
        from src.models.video import TranscriptSegment

        segments = [
            TranscriptSegment(text="Hello", start_seconds=0, end_seconds=1),
            TranscriptSegment(text="world", start_seconds=1, end_seconds=2),
        ]
        result = service.get_full_transcript(segments)
        assert result == "Hello world"
