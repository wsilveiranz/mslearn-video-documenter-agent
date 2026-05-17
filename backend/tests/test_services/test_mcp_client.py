"""Tests for MCP client infrastructure."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.mcp_client import (
    MCPClientManager,
    MCPServerConfig,
    MCPToolResult,
    MCPTransportType,
    _TokenBucket,
)


@pytest.fixture
def http_server_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="learn",
        transport_type=MCPTransportType.STREAMABLE_HTTP,
        endpoint="https://learn.microsoft.com/api/mcp",
        enabled=True,
    )


@pytest.fixture
def stdio_server_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="workiq",
        transport_type=MCPTransportType.STDIO,
        command="npx",
        args=["-y", "@microsoft/workiq", "mcp"],
        enabled=True,
    )


@pytest.fixture
def disabled_server_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="disabled",
        transport_type=MCPTransportType.STREAMABLE_HTTP,
        endpoint="https://example.com/mcp",
        enabled=False,
    )


@pytest.fixture
def manager(http_server_config: MCPServerConfig, stdio_server_config: MCPServerConfig) -> MCPClientManager:
    return MCPClientManager(
        servers={
            "learn": http_server_config,
            "workiq": stdio_server_config,
        },
        cache_ttl=60,
        request_timeout=10,
        graceful_degradation=True,
    )


@pytest.fixture
def manager_with_disabled(
    http_server_config: MCPServerConfig, disabled_server_config: MCPServerConfig
) -> MCPClientManager:
    return MCPClientManager(
        servers={
            "learn": http_server_config,
            "disabled": disabled_server_config,
        },
        cache_ttl=60,
        request_timeout=10,
        graceful_degradation=True,
    )


def _mock_call_tool_result():
    """Create a mock MCP CallToolResult."""
    content_item = MagicMock()
    content_item.type = "text"
    content_item.text = "Azure Functions documentation..."
    result = MagicMock()
    result.content = [content_item]
    result.isError = False
    return result


class TestMCPToolResult:
    """Test MCPToolResult model serialization."""

    def test_default_values(self):
        result = MCPToolResult()
        assert result.available is True
        assert result.data is None
        assert result.cached is False
        assert result.server == ""
        assert result.tool == ""
        assert result.error is None

    def test_serialization(self):
        result = MCPToolResult(
            available=True,
            data={"content": [{"type": "text", "text": "hello"}]},
            cached=False,
            server="learn",
            tool="search",
        )
        dumped = result.model_dump()
        assert dumped["available"] is True
        assert dumped["data"]["content"][0]["text"] == "hello"
        assert dumped["server"] == "learn"

    def test_error_result(self):
        result = MCPToolResult(available=False, error="Connection failed", server="learn", tool="search")
        assert result.available is False
        assert result.error == "Connection failed"


class TestCacheHit:
    """Test cache hit returns cached data without calling MCP."""

    async def test_cache_hit_skips_mcp_call(self, manager: MCPClientManager):
        # Pre-populate cache
        cache_key = manager._get_cache_key("learn", "search", {"query": "azure"})
        cached_data = {"content": [{"type": "text", "text": "cached result"}], "isError": False}
        manager._store_cache(cache_key, cached_data)

        with patch.object(manager, "_execute_tool_call", new_callable=AsyncMock) as mock_execute:
            result = await manager.call_tool("learn", "search", {"query": "azure"})

            mock_execute.assert_not_called()
            assert result.available is True
            assert result.cached is True
            assert result.data == cached_data


class TestCacheMiss:
    """Test cache miss calls MCP and caches the result."""

    async def test_cache_miss_calls_mcp_and_caches(self, manager: MCPClientManager):
        mcp_data = {"content": [{"type": "text", "text": "fresh result"}], "isError": False}

        with patch.object(manager, "_execute_tool_call", new_callable=AsyncMock, return_value=mcp_data):
            result = await manager.call_tool("learn", "search", {"query": "functions"})

            assert result.available is True
            assert result.cached is False
            assert result.data == mcp_data

            # Verify it was cached
            cache_key = manager._get_cache_key("learn", "search", {"query": "functions"})
            assert cache_key in manager._cache


class TestCacheExpiry:
    """Test cache expiry triggers fresh call."""

    async def test_expired_cache_triggers_fresh_call(self, manager: MCPClientManager):
        # Store with expired TTL
        cache_key = manager._get_cache_key("learn", "search", {"query": "expired"})
        expired_data = {"content": [{"type": "text", "text": "stale"}], "isError": False}
        manager._cache[cache_key] = (time.time() - 1, expired_data)  # Already expired

        fresh_data = {"content": [{"type": "text", "text": "fresh"}], "isError": False}

        with patch.object(manager, "_execute_tool_call", new_callable=AsyncMock, return_value=fresh_data):
            result = await manager.call_tool("learn", "search", {"query": "expired"})

            assert result.available is True
            assert result.cached is False
            assert result.data == fresh_data


class TestGracefulDegradation:
    """Test graceful degradation returns unavailable result on connection error."""

    async def test_connection_error_returns_unavailable(self, manager: MCPClientManager):
        with patch.object(
            manager, "_execute_tool_call", new_callable=AsyncMock, side_effect=ConnectionError("Server unreachable")
        ):
            result = await manager.call_tool("learn", "search", {"query": "test"})

            assert result.available is False
            assert result.error == "Server unreachable"
            assert result.server == "learn"
            assert result.tool == "search"

    async def test_timeout_error_returns_unavailable(self, manager: MCPClientManager):
        with patch.object(
            manager, "_execute_tool_call", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()
        ):
            result = await manager.call_tool("learn", "search", {"query": "test"})

            assert result.available is False
            assert result.error is not None

    async def test_graceful_degradation_disabled_raises(self, http_server_config: MCPServerConfig):
        manager = MCPClientManager(
            servers={"learn": http_server_config},
            graceful_degradation=False,
        )
        with patch.object(
            manager, "_execute_tool_call", new_callable=AsyncMock, side_effect=ConnectionError("fail")
        ):
            with pytest.raises(ConnectionError):
                await manager.call_tool("learn", "search", {"query": "test"})


class TestRateLimiting:
    """Test rate limiting behavior."""

    async def test_rate_limit_blocks_excessive_calls(self, manager: MCPClientManager):
        mcp_data = {"content": [{"type": "text", "text": "ok"}], "isError": False}

        with patch.object(manager, "_execute_tool_call", new_callable=AsyncMock, return_value=mcp_data):
            # Exhaust the rate limiter (default 10 tokens)
            results = []
            for i in range(15):
                # Use unique params to avoid cache hits
                result = await manager.call_tool("learn", "search", {"query": f"q{i}"})
                results.append(result)

            # Some should succeed and some should be rate-limited
            rate_limited = [r for r in results if not r.available and r.error == "Rate limited"]
            assert len(rate_limited) > 0

    def test_token_bucket_refill(self):
        bucket = _TokenBucket(rate=600.0, capacity=10.0)  # 600/min = 10/sec
        # Consume all tokens
        for _ in range(10):
            assert bucket.consume() is True
        assert bucket.consume() is False


class TestDisabledServer:
    """Test disabled server returns unavailable result."""

    async def test_disabled_server_returns_unavailable(self, manager_with_disabled: MCPClientManager):
        result = await manager_with_disabled.call_tool("disabled", "search", {"query": "test"})
        assert result.available is False
        assert "disabled" in (result.error or "")

    async def test_unknown_server_returns_unavailable(self, manager: MCPClientManager):
        result = await manager.call_tool("nonexistent", "search", {"query": "test"})
        assert result.available is False
        assert "Unknown server" in (result.error or "")


class TestListTools:
    """Test list_tools functionality."""

    async def test_list_tools_disabled_server(self, manager_with_disabled: MCPClientManager):
        tools = await manager_with_disabled.list_tools("disabled")
        assert tools == []

    async def test_list_tools_graceful_on_error(self, manager: MCPClientManager):
        with patch.object(
            manager, "_execute_list_tools", new_callable=AsyncMock, side_effect=ConnectionError("fail")
        ):
            tools = await manager.list_tools("learn")
            assert tools == []


class TestClose:
    """Test close clears state."""

    async def test_close_clears_cache(self, manager: MCPClientManager):
        manager._cache["key"] = (time.time() + 100, {"data": "value"})
        await manager.close()
        assert len(manager._cache) == 0
