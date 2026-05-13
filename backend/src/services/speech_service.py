"""Azure AI Speech transcription service using the Fast Transcription REST API."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog

from src.config import get_settings
from src.models.video import TranscriptSegment
from src.utils.url import url_join

if TYPE_CHECKING:
    from src.config import Settings

logger = structlog.get_logger()

_COGNITIVESERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
_API_VERSION = "2024-11-15"


class SpeechService:
    """Azure AI Speech transcription service using the Fast Transcription REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._http_client = httpx.AsyncClient(timeout=300.0)

    async def transcribe(
        self,
        audio_source: str | Path,
        *,
        locale: str = "en-US",
        enable_diarization: bool = True,
    ) -> list[TranscriptSegment]:
        """Transcribe audio using the Fast Transcription REST API.

        Args:
            audio_source: Local file path or blob SAS URL.
            locale: Language locale code.
            enable_diarization: Whether to enable speaker attribution.

        Returns:
            List of TranscriptSegment sorted by start time.
        """
        url = (
            f"{url_join(self._settings.speech_service_endpoint, 'speechtotext/transcriptions:transcribe')}"
            f"?api-version={_API_VERSION}"
        )

        token = await self._get_auth_token()
        headers = {"Authorization": f"Bearer {token}"}

        source_str = str(audio_source)
        is_url = source_str.startswith("http://") or source_str.startswith("https://")

        if is_url:
            logger.info(
                "speech.transcription_started",
                operation="transcribe",
                source_type="url",
                locale=locale,
                enable_diarization=enable_diarization,
            )
            response = await self._transcribe_url(url, headers, source_str, locale, enable_diarization)
        else:
            audio_path = Path(audio_source)
            if not audio_path.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            logger.info(
                "speech.transcription_started",
                operation="transcribe",
                source_type="file",
                audio_file=audio_path.name,
                locale=locale,
                enable_diarization=enable_diarization,
            )
            response = await self._transcribe_file(url, headers, audio_path, locale, enable_diarization)

        phrases: list[dict] = response.get("phrases", [])
        segments: list[TranscriptSegment] = []

        for phrase in phrases:
            text = phrase.get("text", "").strip()
            if not text:
                continue

            offset_ms: int = phrase.get("offsetMilliseconds", 0)
            duration_ms: int = phrase.get("durationMilliseconds", 0)
            raw_speaker = phrase.get("speaker")

            segments.append(
                TranscriptSegment(
                    text=text,
                    start_seconds=offset_ms / 1000.0,
                    end_seconds=(offset_ms + duration_ms) / 1000.0,
                    speaker=f"Speaker {raw_speaker}" if raw_speaker is not None else None,
                    confidence=phrase.get("confidence", 1.0),
                )
            )

        segments.sort(key=lambda s: s.start_seconds)

        logger.info(
            "speech.transcription_completed",
            operation="transcribe",
            segment_count=len(segments),
            locale=locale,
        )

        return segments

    async def _transcribe_file(
        self,
        url: str,
        headers: dict[str, str],
        audio_path: Path,
        locale: str,
        enable_diarization: bool,
    ) -> dict:
        """Send audio file bytes as multipart form data."""
        import json

        definition: dict = {
            "locales": [locale],
            "profanityFilterMode": "None",
            "channels": [0, 1],
        }
        if enable_diarization:
            definition["diarizationSettings"] = {"minSpeakers": 1, "maxSpeakers": 4}

        audio_bytes = await asyncio.to_thread(audio_path.read_bytes)

        try:
            response = await self._http_client.post(
                url,
                headers=headers,
                files={
                    "definition": (None, json.dumps(definition), "application/json"),
                    "audio": (audio_path.name, audio_bytes, "application/octet-stream"),
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                "speech.transcription_failed",
                operation="transcribe",
                source_type="file",
                audio_file=audio_path.name,
                status=e.response.status_code,
                error=str(e),
            )
            raise

        return response.json()

    async def _transcribe_url(
        self,
        url: str,
        headers: dict[str, str],
        sas_url: str,
        locale: str,
        enable_diarization: bool,
    ) -> dict:
        """Send a URL-based transcription request as JSON."""
        payload: dict = {
            "contentUrls": [sas_url],
            "locales": [locale],
            "profanityFilterMode": "None",
        }
        if enable_diarization:
            payload["diarizationSettings"] = {"minSpeakers": 1, "maxSpeakers": 4}

        try:
            response = await self._http_client.post(
                url,
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                "speech.transcription_failed",
                operation="transcribe",
                source_type="url",
                status=e.response.status_code,
                error=str(e),
            )
            raise

        return response.json()

    async def _get_auth_token(self) -> str:
        """Get a bearer token for Cognitive Services using DefaultAzureCredential."""
        credential = await asyncio.to_thread(self._settings.get_azure_credential)
        token_result = await asyncio.to_thread(
            credential.get_token, _COGNITIVESERVICES_SCOPE
        )
        return token_result.token

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http_client.aclose()
