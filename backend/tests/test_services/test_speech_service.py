"""Unit tests for SpeechService with mocked HTTP client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.speech_service import SpeechService


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.speech_service_endpoint = "https://eastus.api.cognitive.microsoft.com"
    mock_cred = MagicMock()
    mock_cred.get_token.return_value = MagicMock(token="test-bearer-token")
    s.get_azure_credential.return_value = mock_cred
    return s


@pytest.fixture
def service(mock_settings):
    svc = SpeechService(settings=mock_settings)
    svc._http_client = AsyncMock()
    return svc


def _make_mock_response(phrases: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"phrases": phrases}
    return resp


@pytest.mark.cloud
class TestTranscribeFile:
    async def test_sends_multipart_form_data(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"RIFF fake audio data")

        service._http_client.post = AsyncMock(return_value=_make_mock_response([]))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            await service.transcribe(audio_file)

        call_kwargs = service._http_client.post.call_args.kwargs
        assert "files" in call_kwargs
        assert "audio" in call_kwargs["files"]
        assert "definition" in call_kwargs["files"]

    async def test_definition_includes_locale(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        service._http_client.post = AsyncMock(return_value=_make_mock_response([]))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            await service.transcribe(audio_file, locale="fr-FR")

        call_kwargs = service._http_client.post.call_args.kwargs
        definition = json.loads(call_kwargs["files"]["definition"][1])
        assert "fr-FR" in definition["locales"]

    async def test_maps_phrases_to_transcript_segments(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        phrases = [
            {"text": "Hello world", "offsetMilliseconds": 0, "durationMilliseconds": 2500, "confidence": 0.95},
            {"text": "Second sentence", "offsetMilliseconds": 3000, "durationMilliseconds": 1500, "confidence": 0.88},
        ]
        service._http_client.post = AsyncMock(return_value=_make_mock_response(phrases))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            segments = await service.transcribe(audio_file)

        assert len(segments) == 2
        assert segments[0].text == "Hello world"
        assert segments[0].start_seconds == pytest.approx(0.0)
        assert segments[0].end_seconds == pytest.approx(2.5)
        assert segments[0].confidence == pytest.approx(0.95)
        assert segments[1].text == "Second sentence"
        assert segments[1].start_seconds == pytest.approx(3.0)

    async def test_file_not_found_raises(self, service):
        with pytest.raises(FileNotFoundError):
            await service.transcribe("/nonexistent/audio.wav")

    async def test_http_error_propagates(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        error_resp = MagicMock()
        error_resp.status_code = 401
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=error_resp
        )
        service._http_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await service.transcribe(audio_file)


@pytest.mark.cloud
class TestTranscribeUrl:
    async def test_sends_json_body_with_content_urls(self, service):
        sas_url = "https://storage.blob.core.windows.net/container/video.mp4?sas=token"

        service._http_client.post = AsyncMock(return_value=_make_mock_response([]))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            await service.transcribe(sas_url)

        call_kwargs = service._http_client.post.call_args.kwargs
        assert "json" in call_kwargs
        assert "contentUrls" in call_kwargs["json"]
        assert sas_url in call_kwargs["json"]["contentUrls"]

    async def test_url_with_diarization_includes_settings(self, service):
        sas_url = "https://storage.blob.core.windows.net/container/video.mp4?sas=token"
        service._http_client.post = AsyncMock(return_value=_make_mock_response([]))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            await service.transcribe(sas_url, enable_diarization=True)

        call_kwargs = service._http_client.post.call_args.kwargs
        assert "diarizationSettings" in call_kwargs["json"]

    async def test_url_http_error_propagates(self, service):
        sas_url = "https://storage.blob.core.windows.net/container/video.mp4?sas=token"

        error_resp = MagicMock()
        error_resp.status_code = 403
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=error_resp
        )
        service._http_client.post = AsyncMock(return_value=mock_resp)

        with (
            patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")),
            pytest.raises(httpx.HTTPStatusError),
        ):
            await service.transcribe(sas_url)


@pytest.mark.cloud
class TestDiarization:
    async def test_speaker_id_mapped_to_speaker_name(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        phrases = [
            {"text": "Hello", "offsetMilliseconds": 0, "durationMilliseconds": 1000, "speaker": 1, "confidence": 0.9},
            {
                "text": "World",
                "offsetMilliseconds": 2000,
                "durationMilliseconds": 1000,
                "speaker": 2,
                "confidence": 0.9,
            },
        ]
        service._http_client.post = AsyncMock(return_value=_make_mock_response(phrases))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            segments = await service.transcribe(audio_file)

        assert segments[0].speaker == "Speaker 1"
        assert segments[1].speaker == "Speaker 2"

    async def test_no_speaker_field_gives_none_speaker(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        phrases = [
            {"text": "Hello", "offsetMilliseconds": 0, "durationMilliseconds": 1000, "confidence": 0.9},
        ]
        service._http_client.post = AsyncMock(return_value=_make_mock_response(phrases))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            segments = await service.transcribe(audio_file)

        assert segments[0].speaker is None


@pytest.mark.cloud
class TestEmptyResponse:
    async def test_empty_phrases_returns_empty_list(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        service._http_client.post = AsyncMock(return_value=_make_mock_response([]))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            segments = await service.transcribe(audio_file)

        assert segments == []

    async def test_whitespace_only_phrases_are_skipped(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        phrases = [
            {"text": "   ", "offsetMilliseconds": 0, "durationMilliseconds": 500, "confidence": 0.5},
            {"text": "Real text", "offsetMilliseconds": 1000, "durationMilliseconds": 1000, "confidence": 0.9},
        ]
        service._http_client.post = AsyncMock(return_value=_make_mock_response(phrases))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            segments = await service.transcribe(audio_file)

        assert len(segments) == 1
        assert segments[0].text == "Real text"

    async def test_segments_sorted_by_start_time(self, service, tmp_path):
        audio_file = tmp_path / "audio.wav"
        audio_file.write_bytes(b"fake audio")

        # Return phrases out of order
        phrases = [
            {"text": "Second", "offsetMilliseconds": 3000, "durationMilliseconds": 1000, "confidence": 0.9},
            {"text": "First", "offsetMilliseconds": 0, "durationMilliseconds": 1000, "confidence": 0.9},
        ]
        service._http_client.post = AsyncMock(return_value=_make_mock_response(phrases))

        with patch.object(service, "_get_auth_token", AsyncMock(return_value="fake_token")):
            segments = await service.transcribe(audio_file)

        assert segments[0].text == "First"
        assert segments[1].text == "Second"
