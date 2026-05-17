"""Tests for Work IQ MCP tool wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.mcp_client import MCPServerConfig, MCPToolResult, MCPTransportType
from src.services.workiq_mcp_tools import (
    WORKIQ_MCP_SERVER,
    M365Document,
    M365SearchResult,
    WorkIQTools,
)


def _make_mock_manager(tool_result: MCPToolResult | None = None) -> MagicMock:
    manager = MagicMock()
    manager._servers = {
        WORKIQ_MCP_SERVER: MCPServerConfig(
            name=WORKIQ_MCP_SERVER,
            transport_type=MCPTransportType.STDIO,
            command="npx",
            args=["-y", "@microsoft/workiq", "mcp"],
        )
    }
    if tool_result:
        manager.call_tool = AsyncMock(return_value=tool_result)
    else:
        manager.call_tool = AsyncMock(return_value=MCPToolResult(available=False))
    return manager


class TestWorkIQTools:
    async def test_search_context_returns_result(self):
        result = MCPToolResult(
            available=True,
            data={"content": [{"text": "The project deadline was discussed in yesterday's meeting. Key decisions: ..."}]},
            server=WORKIQ_MCP_SERVER,
            tool="ask",
        )
        tools = WorkIQTools(_make_mock_manager(result))
        search_result = await tools.search_context("project deadline discussion")

        assert search_result.available
        assert search_result.summary
        assert len(search_result.documents) > 0

    async def test_search_context_unavailable(self):
        tools = WorkIQTools(_make_mock_manager())
        result = await tools.search_context("anything")
        assert not result.available

    async def test_search_documents(self):
        result = MCPToolResult(
            available=True,
            data={"text": "Found specification document for portal project..."},
            server=WORKIQ_MCP_SERVER,
            tool="ask",
        )
        tools = WorkIQTools(_make_mock_manager(result))
        docs = await tools.search_documents("portal specification")
        assert len(docs) > 0

    async def test_available_property(self):
        tools = WorkIQTools(_make_mock_manager())
        assert tools.available

    async def test_available_false_when_not_configured(self):
        manager = MagicMock()
        manager._servers = {}
        tools = WorkIQTools(manager)
        assert not tools.available

    async def test_search_context_with_string_content(self):
        result = MCPToolResult(
            available=True,
            data={"content": "Summary of meeting notes about the project..."},
            server=WORKIQ_MCP_SERVER,
            tool="ask",
        )
        tools = WorkIQTools(_make_mock_manager(result))
        search_result = await tools.search_context("meeting notes")
        assert search_result.available
        assert search_result.summary

    async def test_search_context_empty_response(self):
        result = MCPToolResult(
            available=True,
            data={},
            server=WORKIQ_MCP_SERVER,
            tool="ask",
        )
        tools = WorkIQTools(_make_mock_manager(result))
        search_result = await tools.search_context("nonexistent topic")
        assert search_result.available
        assert search_result.summary == ""
