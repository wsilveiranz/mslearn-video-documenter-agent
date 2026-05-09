"""Local transcription service using OpenAI Whisper."""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from src.config import get_settings
from src.models.video import TranscriptSegment

logger = structlog.get_logger()


def _ensure_ffmpeg_on_path() -> None:
    """Add the configured FFMPEG_PATH directory to PATH so Whisper can find ffmpeg."""
    settings = get_settings()
    ffmpeg_path = getattr(settings, "ffmpeg_path", None)
    if not ffmpeg_path:
        return
    ffmpeg_dir = str(Path(ffmpeg_path).parent)
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir not in current_path:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
        logger.debug("whisper.ffmpeg_path_added", ffmpeg_dir=ffmpeg_dir)


class WhisperService:
    """Transcribes audio files using a locally-loaded OpenAI Whisper model.

    Model loading is lazy — the model is downloaded and cached on the first
    call to ``transcribe()``. Subsequent calls reuse the cached model.

    Note: ``transcribe()`` is CPU-heavy and synchronous. Callers should
    offload it to a thread pool via ``asyncio.to_thread()``.
    """

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self._model_name = model_name or settings.whisper_model or "base"
        self._model = None

    def _load_model(self) -> None:
        """Lazy-load and cache the Whisper model."""
        if self._model is not None:
            return

        try:
            import whisper  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                'Whisper is not installed. Run: pip install "mslearn-video-documenter[local]"'
            ) from exc

        logger.info("whisper_model_loading", operation="load_model", model=self._model_name)
        self._model = whisper.load_model(self._model_name)
        logger.info("whisper_model_loaded", operation="load_model", model=self._model_name)

    def transcribe(self, audio_path: str | Path) -> list[TranscriptSegment]:
        """Transcribe an audio file and return timestamped segments.

        Args:
            audio_path: Path to the audio file to transcribe.

        Returns:
            List of ``TranscriptSegment`` objects sorted by start time.
            Returns an empty list when no speech is detected.

        Raises:
            FileNotFoundError: If ``audio_path`` does not exist.
            ImportError: If the ``whisper`` package is not installed.
            RuntimeError: If Whisper transcription fails unexpectedly.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        self._load_model()

        logger.info(
            "whisper_transcription_started",
            operation="transcribe",
            audio_path=audio_path.name,
            model=self._model_name,
        )

        _ensure_ffmpeg_on_path()

        try:
            result = self._model.transcribe(str(audio_path))
        except Exception as exc:
            logger.error(
                "whisper_transcription_failed",
                operation="transcribe",
                audio_path=audio_path.name,
                error=str(exc),
            )
            raise RuntimeError(f"Whisper transcription failed for {audio_path.name}") from exc

        raw_segments: list[dict] = result.get("segments", [])

        segments: list[TranscriptSegment] = []
        for seg in raw_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue

            confidence = 1.0 - seg.get("no_speech_prob", 0.0)

            segments.append(
                TranscriptSegment(
                    text=text,
                    start_seconds=seg["start"],
                    end_seconds=seg["end"],
                    speaker=None,
                    confidence=confidence,
                )
            )

        segments.sort(key=lambda s: s.start_seconds)

        logger.info(
            "whisper_transcription_completed",
            operation="transcribe",
            audio_path=audio_path.name,
            segment_count=len(segments),
        )

        return segments

    def get_full_transcript(self, segments: list[TranscriptSegment]) -> str:
        """Join all segment texts into a single string for use in LLM prompts.

        Args:
            segments: List of transcript segments.

        Returns:
            Space-joined transcript text.
        """
        return " ".join(seg.text for seg in segments)
