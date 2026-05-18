"""MCP client infrastructure — generic client for connecting to MCP servers."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class MCPTransportType(StrEnum):
    """Supported MCP transport types."""

    STREAMABLE_HTTP = "streamable_http"
    STDIO = "stdio"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection."""

    name: str
    transport_type: MCPTransportType
    endpoint: str = ""  # For Streamable HTTP
    command: str = ""  # For stdio
    args: list[str] = field(default_factory=list)  # For stdio
    enabled: bool = True


class MCPToolResult(BaseModel):
    """Result from an MCP tool call."""

    available: bool = True
    data: dict[str, Any] | None = None
    cached: bool = False
    server: str = ""
    tool: str = ""
    error: str | None = None


class _TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float = 10.0, capacity: float = 10.0) -> None:
        self._rate = rate  # tokens per minute
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate-limited."""
        now = time.monotonic()
        elapsed_minutes = (now - self._last_refill) / 60.0
        self._tokens = min(self._capacity, self._tokens + elapsed_minutes * self._rate)
        self._last_refill = now

        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class MCPClientManager:
    """Manages connections to MCP servers with caching and graceful degradation."""

    def __init__(
        self,
        servers: dict[str, MCPServerConfig],
        cache_ttl: int = 3600,
        request_timeout: int = 30,
        graceful_degradation: bool = True,
    ) -> None:
        self._servers = servers
        self._cache_ttl = cache_ttl
        self._request_timeout = request_timeout
        self._graceful_degradation = graceful_degradation
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}  # key → (expiry_timestamp, data)
        self._rate_limiters: dict[str, _TokenBucket] = {}

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        params: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """Call a tool on an MCP server with caching and error handling."""
        params = params or {}

        # Check server exists and is enabled
        server_config = self._servers.get(server_name)
        if not server_config:
            return MCPToolResult(
                available=False,
                server=server_name,
                tool=tool_name,
                error=f"Unknown server: {server_name}",
            )
        if not server_config.enabled:
            return MCPToolResult(
                available=False,
                server=server_name,
                tool=tool_name,
                error=f"Server '{server_name}' is disabled",
            )

        # Check cache
        cache_key = self._get_cache_key(server_name, tool_name, params)
        cached = self._check_cache(cache_key)
        if cached is not None:
            return cached

        # Check rate limit
        limiter = self._rate_limiters.setdefault(server_name, _TokenBucket())
        if not limiter.consume():
            logger.warning("mcp_rate_limited", server=server_name, tool=tool_name)
            return MCPToolResult(
                available=False,
                server=server_name,
                tool=tool_name,
                error="Rate limited",
            )

        # Call the MCP server
        try:
            data = await self._execute_tool_call(server_config, tool_name, params)
            if data.get("isError", False):
                logger.warning("mcp_tool_reported_error", server=server_name, tool=tool_name)
                if self._graceful_degradation:
                    return MCPToolResult(
                        available=False,
                        server=server_name,
                        tool=tool_name,
                        error="Tool reported an error",
                    )
                raise RuntimeError(f"MCP tool '{tool_name}' on server '{server_name}' reported an error")
            self._store_cache(cache_key, data)
            logger.info("mcp_tool_called", server=server_name, tool=tool_name)
            return MCPToolResult(
                available=True,
                data=data,
                cached=False,
                server=server_name,
                tool=tool_name,
            )
        except Exception as e:
            logger.warning("mcp_call_failed", server=server_name, tool=tool_name, error=str(e))
            if self._graceful_degradation:
                return MCPToolResult(
                    available=False,
                    server=server_name,
                    tool=tool_name,
                    error=str(e),
                )
            raise

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """List available tools on a server."""
        server_config = self._servers.get(server_name)
        if not server_config or not server_config.enabled:
            return []

        try:
            return await self._execute_list_tools(server_config)
        except Exception as e:
            logger.warning("mcp_list_tools_failed", server=server_name, error=str(e))
            if self._graceful_degradation:
                return []
            raise

    async def _execute_tool_call(
        self,
        config: MCPServerConfig,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call against the appropriate transport."""
        import asyncio

        from mcp import ClientSession

        if config.transport_type == MCPTransportType.STREAMABLE_HTTP:
            from mcp.client.streamable_http import streamablehttp_client

            async def _do_http_call() -> dict[str, Any]:
                async with (
                    streamablehttp_client(url=config.endpoint) as (read_stream, write_stream, _),
                    ClientSession(read_stream, write_stream) as session,
                ):
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=params)
                    return self._parse_tool_result(result)

            return await asyncio.wait_for(_do_http_call(), timeout=self._request_timeout)
        else:
            from mcp.client.stdio import StdioServerParameters, stdio_client

            server_params = StdioServerParameters(command=config.command, args=config.args)

            async def _do_stdio_call() -> dict[str, Any]:
                async with (
                    stdio_client(server_params) as (read_stream, write_stream),
                    ClientSession(read_stream, write_stream) as session,
                ):
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=params)
                    return self._parse_tool_result(result)

            return await asyncio.wait_for(_do_stdio_call(), timeout=self._request_timeout)

    async def _execute_list_tools(self, config: MCPServerConfig) -> list[dict[str, Any]]:
        """List tools from the appropriate transport."""
        from mcp import ClientSession

        if config.transport_type == MCPTransportType.STREAMABLE_HTTP:
            from mcp.client.streamable_http import streamablehttp_client

            async with (
                streamablehttp_client(url=config.endpoint) as (read_stream, write_stream, _),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                result = await session.list_tools()
                return [{"name": t.name, "description": t.description} for t in result.tools]
        else:
            from mcp.client.stdio import StdioServerParameters, stdio_client

            server_params = StdioServerParameters(command=config.command, args=config.args)
            async with (
                stdio_client(server_params) as (read_stream, write_stream),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                result = await session.list_tools()
                return [{"name": t.name, "description": t.description} for t in result.tools]

    @staticmethod
    def _parse_tool_result(result: Any) -> dict[str, Any]:
        """Parse an MCP CallToolResult into a plain dict.

        Preserves all available structured fields (title, url, language, code, etc.)
        from content items, not just type and text.
        """
        contents: list[dict[str, Any]] = []
        for content in result.content:
            item: dict[str, Any] = {"type": content.type, "text": getattr(content, "text", "")}
            # Preserve any additional structured fields from the content item
            for attr in ("title", "url", "language", "code", "description", "name"):
                val = getattr(content, attr, None)
                if val is not None:
                    item[attr] = val
            # Also capture annotations/metadata if present
            if hasattr(content, "annotations") and content.annotations:
                item["annotations"] = content.annotations
            contents.append(item)
        return {"content": contents, "isError": getattr(result, "isError", False)}

    def _get_cache_key(self, server: str, tool: str, params: dict[str, Any]) -> str:
        """Generate a deterministic cache key."""
        raw = json.dumps({"server": server, "tool": tool, "params": params}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _check_cache(self, key: str) -> MCPToolResult | None:
        """Return cached result if valid, or None."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        expiry, data = entry
        if time.time() > expiry:
            del self._cache[key]
            return None
        return MCPToolResult(
            available=True,
            data=data,
            cached=True,
            server=data.get("_server", ""),
            tool=data.get("_tool", ""),
        )

    def _store_cache(self, key: str, data: dict[str, Any]) -> None:
        """Store a result in the cache with TTL."""
        expiry = time.time() + self._cache_ttl
        self._cache[key] = (expiry, data)

    async def close(self) -> None:
        """Close all active sessions and clear cache."""
        self._cache.clear()
        logger.info("mcp_client_manager_closed")
