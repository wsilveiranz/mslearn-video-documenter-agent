"""Copilot LM Proxy client — routes LLM calls through VS Code Copilot models.

Implements the ``SupportsChatGetResponse`` protocol from ``agent_framework``
so it can be used as a drop-in replacement for ``FoundryChatClient`` in all
agents and service calls.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from agent_framework import ChatResponse, Content, Message

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

logger = structlog.get_logger()

# Retry configuration
_MAX_RETRIES = 3
_INITIAL_BACKOFF_S = 1.0
_RETRYABLE_STATUS_CODES = {429, 503, 502, 504}
_REQUEST_TIMEOUT_S = 120.0


class CopilotProxyError(Exception):
    """Raised when the Copilot LM Proxy returns an unrecoverable error."""


class CopilotProxyUnreachableError(CopilotProxyError):
    """Raised when the Copilot LM Proxy cannot be reached."""


class _CompletionMessage:
    """Mimics ``openai.types.chat.ChatCompletionMessage``."""

    __slots__ = ("content", "role")

    def __init__(self, content: str, role: str = "assistant") -> None:
        self.content = content
        self.role = role


class _CompletionChoice:
    """Mimics ``openai.types.chat.ChatCompletionChoice``."""

    __slots__ = ("finish_reason", "index", "message")

    def __init__(self, message: _CompletionMessage, finish_reason: str = "stop", index: int = 0) -> None:
        self.message = message
        self.finish_reason = finish_reason
        self.index = index


class _CompletionResponse:
    """Mimics ``openai.types.chat.ChatCompletion``.

    Returned by :meth:`CopilotProxyChatClient.complete` so that call sites
    like ``editor.py`` can access ``response.choices[0].message.content``.
    """

    __slots__ = ("choices", "model")

    def __init__(self, choices: list[_CompletionChoice], model: str) -> None:
        self.choices = choices
        self.model = model


# ---------------------------------------------------------------------------
# Message translation helpers
# ---------------------------------------------------------------------------

def _content_to_openai(content: Content) -> dict[str, Any]:
    """Convert a single ``Content`` item to OpenAI message content dict."""
    if content.type == "text":
        return {"type": "text", "text": content.text or ""}

    if content.type == "data":
        # Content.from_data stores data as a base64 data URI in content.uri
        return {
            "type": "image_url",
            "image_url": {"url": content.uri or ""},
        }

    if content.type == "uri":
        return {
            "type": "image_url",
            "image_url": {"url": content.uri or ""},
        }

    # Fallback: try to represent as text
    return {"type": "text", "text": content.text or str(content)}


def _message_to_openai(msg: Message) -> dict[str, Any]:
    """Convert an ``agent_framework.Message`` to an OpenAI-compatible dict."""
    parts: list[dict[str, Any]] = [_content_to_openai(c) for c in msg.contents]

    # If every part is plain text, collapse to a single string for simpler payloads
    if all(p["type"] == "text" for p in parts):
        combined_text = " ".join(p["text"] for p in parts)
        return {"role": msg.role, "content": combined_text}

    return {"role": msg.role, "content": parts}


def _openai_response_to_chat_response(data: dict[str, Any], model: str) -> ChatResponse[Any]:
    """Wrap a raw OpenAI-format JSON response in an ``agent_framework.ChatResponse``."""
    choices = data.get("choices", [])
    if not choices:
        return ChatResponse(
            messages=[Message("assistant", [""])],
            model=model,
            finish_reason="stop",
        )

    first_choice = choices[0]
    message_data = first_choice.get("message", {})
    text = message_data.get("content", "") or ""
    finish_reason = first_choice.get("finish_reason", "stop")

    return ChatResponse(
        messages=[Message("assistant", [text])],
        model=model,
        finish_reason=finish_reason,
    )


# ---------------------------------------------------------------------------
# CopilotProxyChatClient
# ---------------------------------------------------------------------------

class CopilotProxyChatClient:
    """Chat client that forwards requests to the VS Code Copilot LM Proxy.

    Implements the ``SupportsChatGetResponse`` protocol so it works as the
    ``client`` parameter for ``Agent(client=...)`` and for direct
    ``client.get_response(messages=...)`` calls throughout the pipeline.

    Args:
        proxy_url: Base URL of the LM Proxy server (e.g. ``http://localhost:3000``).
        model: Model identifier to request (default ``copilot-auto``).
    """

    def __init__(self, proxy_url: str, model: str = "copilot-auto", secret: str = "") -> None:
        self._proxy_url = proxy_url.rstrip("/")
        self.model = model
        self._secret = secret
        # Required by the SupportsChatGetResponse protocol
        self.additional_properties: dict[str, Any] = {}

        self._http_client = httpx.AsyncClient(
            base_url=self._proxy_url,
            timeout=httpx.Timeout(_REQUEST_TIMEOUT_S, connect=10.0),
        )
        logger.info(
            "copilot_client.init",
            operation="init",
            proxy_url=self._proxy_url,
            model=self.model,
        )

    # ------------------------------------------------------------------
    # SupportsChatGetResponse protocol
    # ------------------------------------------------------------------

    def get_response(
        self,
        messages: Sequence[Message],
        *,
        stream: bool = False,
        options: Any | None = None,
        compaction_strategy: Any | None = None,
        tokenizer: Any | None = None,
        function_invocation_kwargs: Mapping[str, Any] | None = None,
        client_kwargs: Mapping[str, Any] | None = None,
    ) -> Any:
        """Return an awaitable ``ChatResponse`` (non-streaming only).

        This matches the ``SupportsChatGetResponse`` protocol signature.
        Streaming is not yet supported; passing ``stream=True`` raises
        ``NotImplementedError``.
        """
        if stream:
            raise NotImplementedError(
                "CopilotProxyChatClient does not support streaming yet. "
                "Use stream=False (the default)."
            )
        return self._get_response_async(messages)

    # ------------------------------------------------------------------
    # Core async implementation
    # ------------------------------------------------------------------

    async def _get_response_async(
        self,
        messages: Sequence[Message],
    ) -> ChatResponse[Any]:
        """Translate messages, call the proxy, and return a ``ChatResponse``."""
        openai_messages = [_message_to_openai(m) for m in messages]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
        }

        logger.debug(
            "copilot_client.request",
            operation="get_response",
            model=self.model,
            message_count=len(openai_messages),
        )

        data = await self._post_with_retry("/v1/chat/completions", payload)
        response = _openai_response_to_chat_response(data, self.model)

        logger.info(
            "copilot_client.response",
            operation="get_response",
            model=self.model,
            response_length=len(response.text),
            finish_reason=response.finish_reason,
        )
        return response

    # ------------------------------------------------------------------
    # OpenAI-compatible .complete() for editor fallback
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        **kwargs: Any,
    ) -> _CompletionResponse:
        """OpenAI-compatible completion for call sites using dict-style messages.

        The editor agent's fallback path calls::

            response = await client.complete(messages=[{"role": ..., "content": ...}])
            text = response.choices[0].message.content

        This method accepts those raw dicts (no ``agent_framework.Message``
        conversion needed) and returns a ``_CompletionResponse`` with the
        same shape as an ``openai.ChatCompletion``.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            **kwargs,
        }

        logger.debug(
            "copilot_client.complete_request",
            operation="complete",
            model=self.model,
            message_count=len(messages),
        )

        data = await self._post_with_retry("/v1/chat/completions", payload)

        choices_data = data.get("choices", [])
        choices: list[_CompletionChoice] = []
        for i, choice in enumerate(choices_data):
            msg_data = choice.get("message", {})
            text = msg_data.get("content", "") or ""
            finish = choice.get("finish_reason", "stop")
            choices.append(
                _CompletionChoice(
                    message=_CompletionMessage(content=text),
                    finish_reason=finish,
                    index=i,
                )
            )

        if not choices:
            choices.append(
                _CompletionChoice(message=_CompletionMessage(content=""))
            )

        response = _CompletionResponse(choices=choices, model=self.model)

        logger.info(
            "copilot_client.complete_response",
            operation="complete",
            model=self.model,
            response_length=len(response.choices[0].message.content),
        )
        return response

    # ------------------------------------------------------------------
    # HTTP helpers with retry
    # ------------------------------------------------------------------

    async def _post_with_retry(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to the proxy with exponential backoff on transient errors."""
        last_exc: Exception | None = None
        backoff = _INITIAL_BACKOFF_S

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                if self._secret:
                    headers["Authorization"] = f"Bearer {self._secret}"

                resp = await self._http_client.post(
                    path,
                    json=payload,
                    headers=headers,
                )

                if resp.status_code in _RETRYABLE_STATUS_CODES:
                    body_preview = resp.text[:200]
                    logger.warning(
                        "copilot_client.retryable_error",
                        operation="post",
                        status=resp.status_code,
                        attempt=attempt,
                        body_preview=body_preview,
                    )
                    last_exc = CopilotProxyError(
                        f"Proxy returned {resp.status_code}: {body_preview}"
                    )
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    raise last_exc

                if resp.status_code >= 500:
                    body_preview = resp.text[:200]
                    logger.warning(
                        "copilot_client.server_error",
                        operation="post",
                        status=resp.status_code,
                        attempt=attempt,
                        body_preview=body_preview,
                    )
                    last_exc = CopilotProxyError(
                        f"Proxy server error {resp.status_code}: {body_preview}"
                    )
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    raise last_exc

                if resp.status_code >= 400:
                    body_preview = resp.text[:500]
                    raise CopilotProxyError(
                        f"Proxy returned client error {resp.status_code}: {body_preview}"
                    )

                return resp.json()

            except httpx.ConnectError as exc:
                logger.error(
                    "copilot_client.unreachable",
                    operation="post",
                    proxy_url=self._proxy_url,
                    attempt=attempt,
                    error=str(exc),
                )
                last_exc = CopilotProxyUnreachableError(
                    f"Cannot reach Copilot LM Proxy at {self._proxy_url}. "
                    "Is the VS Code LM Proxy server running? "
                    f"(attempt {attempt}/{_MAX_RETRIES})"
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise last_exc from exc

            except httpx.TimeoutException as exc:
                logger.error(
                    "copilot_client.timeout",
                    operation="post",
                    proxy_url=self._proxy_url,
                    attempt=attempt,
                    error=str(exc),
                )
                last_exc = CopilotProxyError(
                    f"Request to Copilot LM Proxy timed out after {_REQUEST_TIMEOUT_S}s "
                    f"(attempt {attempt}/{_MAX_RETRIES})"
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise last_exc from exc

        # Should not reach here, but guard against it
        raise last_exc or CopilotProxyError("All retry attempts exhausted")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http_client.aclose()
        logger.debug("copilot_client.closed", operation="close")

    async def __aenter__(self) -> CopilotProxyChatClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def create_copilot_client(proxy_url: str, model: str = "copilot-auto", secret: str = "") -> CopilotProxyChatClient:
    """Create a ``CopilotProxyChatClient`` instance.

    This is the local-mode equivalent of ``create_foundry_client()`` in
    ``orchestrator.py``.

    Args:
        proxy_url: Base URL of the VS Code LM Proxy (e.g. ``http://localhost:3000``).
        model: Model identifier to request (default ``copilot-auto``).

    Returns:
        A configured ``CopilotProxyChatClient`` ready to be passed to agents.
    """
    return CopilotProxyChatClient(proxy_url=proxy_url, model=model, secret=secret)
