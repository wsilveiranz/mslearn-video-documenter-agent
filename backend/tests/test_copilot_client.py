"""Tests for CopilotProxyChatClient.

Uses httpx.MockTransport for HTTP-level mocking (no extra deps needed)
and unittest.mock for connection-error scenarios.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from agent_framework import Content, Message

from src.services.copilot_client import (
    CopilotProxyChatClient,
    CopilotProxyError,
    CopilotProxyUnreachableError,
    _content_to_openai,
    _message_to_openai,
    _openai_response_to_chat_response,
)

PROXY_URL = "http://localhost:3000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_chat_response(content: str = "Hello!", finish_reason: str = "stop") -> dict[str, Any]:
    """Build a minimal OpenAI-format chat completion response."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _make_transport(handler):
    """Create an httpx.MockTransport from an async handler function."""
    return httpx.MockTransport(handler)


def _replace_transport(client: CopilotProxyChatClient, handler) -> None:
    """Swap the internal httpx client's transport with a mock."""
    client._http_client = httpx.AsyncClient(
        base_url=PROXY_URL,
        transport=_make_transport(handler),
        timeout=httpx.Timeout(10.0),
    )


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContentToOpenAI:
    """Tests for the _content_to_openai helper."""

    def test_text_content(self):
        c = Content(type="text", text="hello")
        result = _content_to_openai(c)
        assert result == {"type": "text", "text": "hello"}

    def test_data_content_with_base64_uri(self):
        c = Content.from_data(b"image-bytes", "image/png")
        result = _content_to_openai(c)
        assert result["type"] == "image_url"
        assert "base64" in result["image_url"]["url"]

    def test_fallback_content(self):
        c = Content(type="text", text=None)
        result = _content_to_openai(c)
        assert result == {"type": "text", "text": ""}


@pytest.mark.unit
class TestMessageToOpenAI:
    """Tests for the _message_to_openai helper."""

    def test_single_text_collapses_to_string(self):
        msg = Message("user", ["describe this image"])
        result = _message_to_openai(msg)
        assert result["role"] == "user"
        assert isinstance(result["content"], str)
        assert result["content"] == "describe this image"

    def test_mixed_content_keeps_parts(self):
        image = Content.from_data(b"img-data", "image/png")
        msg = Message("user", [Content(type="text", text="describe"), image])
        result = _message_to_openai(msg)
        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 2
        assert result["content"][0]["type"] == "text"
        assert result["content"][1]["type"] == "image_url"

    def test_system_role_preserved(self):
        msg = Message("system", ["You are helpful."])
        result = _message_to_openai(msg)
        assert result["role"] == "system"

    def test_assistant_role_preserved(self):
        msg = Message("assistant", ["Sure, I can help."])
        result = _message_to_openai(msg)
        assert result["role"] == "assistant"


@pytest.mark.unit
class TestOpenAIResponseToChatResponse:
    """Tests for _openai_response_to_chat_response."""

    def test_basic_response(self):
        data = _openai_chat_response("Hello world")
        cr = _openai_response_to_chat_response(data, "copilot-auto")
        assert cr.text == "Hello world"
        assert cr.model == "copilot-auto"
        assert cr.finish_reason == "stop"

    def test_empty_choices_returns_empty_text(self):
        data = {"choices": []}
        cr = _openai_response_to_chat_response(data, "gpt-4o")
        assert cr.text == ""
        assert cr.finish_reason == "stop"

    def test_missing_choices_key(self):
        data = {}
        cr = _openai_response_to_chat_response(data, "gpt-4o")
        assert cr.text == ""


# ---------------------------------------------------------------------------
# Integration tests — CopilotProxyChatClient
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTextCompletionSuccess:
    """test_text_completion_success — text-only message, verify request + response."""

    @pytest.mark.asyncio
    async def test_text_completion_success(self):
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json=_openai_chat_response("The answer is 42."))

        client = CopilotProxyChatClient(proxy_url=PROXY_URL, model="copilot-auto")
        _replace_transport(client, handler)

        messages = [Message("user", ["What is the meaning of life?"])]
        response = await client.get_response(messages)

        assert response.text == "The answer is 42."
        assert response.finish_reason == "stop"

        # Verify request payload
        assert len(captured_requests) == 1
        body = json.loads(captured_requests[0].content)
        assert body["model"] == "copilot-auto"
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"
        assert "meaning of life" in body["messages"][0]["content"]

        await client.close()


@pytest.mark.unit
class TestVisionMessageWithImage:
    """test_vision_message_with_image — base64 image in request payload."""

    @pytest.mark.asyncio
    async def test_vision_message_with_image(self):
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json=_openai_chat_response("I see a screenshot."))

        client = CopilotProxyChatClient(proxy_url=PROXY_URL, model="gpt-4o")
        _replace_transport(client, handler)

        image_content = Content.from_data(b"\x89PNG\r\n\x1a\nfake-png-data", "image/png")
        messages = [
            Message("user", [Content(type="text", text="Describe this image"), image_content]),
        ]
        response = await client.get_response(messages)

        assert response.text == "I see a screenshot."

        body = json.loads(captured_requests[0].content)
        msg_content = body["messages"][0]["content"]
        assert isinstance(msg_content, list)
        assert msg_content[0]["type"] == "text"
        assert msg_content[1]["type"] == "image_url"
        assert "base64" in msg_content[1]["image_url"]["url"]

        await client.close()


@pytest.mark.unit
class TestRetryOn429:
    """test_retry_on_429 — 429 then success, verify retry logic."""

    @pytest.mark.asyncio
    async def test_retry_on_429(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, text="Rate limited")
            return httpx.Response(200, json=_openai_chat_response("Success after retry"))

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        with patch("src.services.copilot_client.asyncio.sleep", new_callable=AsyncMock):
            response = await client.get_response([Message("user", ["hello"])])

        assert response.text == "Success after retry"
        assert call_count == 2

        await client.close()


@pytest.mark.unit
class TestRetryOn503:
    """test_retry_on_503 — 503 then success."""

    @pytest.mark.asyncio
    async def test_retry_on_503(self):
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(200, json=_openai_chat_response("Back online"))

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        with patch("src.services.copilot_client.asyncio.sleep", new_callable=AsyncMock):
            response = await client.get_response([Message("user", ["ping"])])

        assert response.text == "Back online"
        assert call_count == 2

        await client.close()


@pytest.mark.unit
class TestProxyUnreachableError:
    """test_proxy_unreachable_error — connection refused raises CopilotProxyUnreachableError."""

    @pytest.mark.asyncio
    async def test_proxy_unreachable_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        with (
            patch("src.services.copilot_client.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(CopilotProxyUnreachableError, match="Cannot reach Copilot LM Proxy"),
        ):
            await client.get_response([Message("user", ["hello"])])

        await client.close()


@pytest.mark.unit
class TestProxyErrorResponse:
    """test_proxy_error_response — 400 error with detail body."""

    @pytest.mark.asyncio
    async def test_proxy_error_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400,
                text='{"error": "Invalid model specified"}',
            )

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        with pytest.raises(CopilotProxyError, match="client error 400"):
            await client.get_response([Message("user", ["hello"])])

        await client.close()


@pytest.mark.unit
class TestSystemMessageHandling:
    """test_system_message_handling — system role is correctly translated."""

    @pytest.mark.asyncio
    async def test_system_message_handling(self):
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json=_openai_chat_response("OK"))

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        messages = [
            Message("system", ["You are a helpful documentation assistant."]),
            Message("user", ["Write a quickstart guide."]),
        ]
        await client.get_response(messages)

        body = json.loads(captured_requests[0].content)
        assert body["messages"][0]["role"] == "system"
        assert "documentation assistant" in body["messages"][0]["content"]
        assert body["messages"][1]["role"] == "user"

        await client.close()


@pytest.mark.unit
class TestMultiMessageConversation:
    """test_multi_message_conversation — system + user + assistant + user roles mapped correctly."""

    @pytest.mark.asyncio
    async def test_multi_message_conversation(self):
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json=_openai_chat_response("Final response"))

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        messages = [
            Message("system", ["You are an expert."]),
            Message("user", ["What is Azure?"]),
            Message("assistant", ["Azure is a cloud platform."]),
            Message("user", ["Tell me more about App Service."]),
        ]
        response = await client.get_response(messages)

        assert response.text == "Final response"

        body = json.loads(captured_requests[0].content)
        assert len(body["messages"]) == 4
        assert [m["role"] for m in body["messages"]] == [
            "system",
            "user",
            "assistant",
            "user",
        ]

        await client.close()


@pytest.mark.unit
class TestRetryExhaustion:
    """Verify that all retries exhausted raises CopilotProxyError."""

    @pytest.mark.asyncio
    async def test_retry_exhaustion_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="Rate limited forever")

        client = CopilotProxyChatClient(proxy_url=PROXY_URL)
        _replace_transport(client, handler)

        with (
            patch("src.services.copilot_client.asyncio.sleep", new_callable=AsyncMock),
            pytest.raises(CopilotProxyError, match="429"),
        ):
            await client.get_response([Message("user", ["hello"])])

        await client.close()


@pytest.mark.unit
class TestContextManager:
    """Verify async context manager closes the client."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_openai_chat_response("OK"))

        async with CopilotProxyChatClient(proxy_url=PROXY_URL) as client:
            _replace_transport(client, handler)
            response = await client.get_response([Message("user", ["hi"])])
            assert response.text == "OK"


@pytest.mark.unit
class TestStreamingNotSupported:
    """Verify stream=True raises NotImplementedError."""

    @pytest.mark.asyncio
    async def test_streaming_raises_not_implemented(self):
        client = CopilotProxyChatClient(proxy_url=PROXY_URL)

        with pytest.raises(NotImplementedError, match="does not support streaming"):
            await client.get_response([Message("user", ["hi"])], stream=True)

        await client.close()
