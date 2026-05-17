"""Tests for Microsoft Learn MCP tool wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.learn_mcp_tools import (
    CodeSample,
    DocContent,
    DocSearchResult,
    LearnMCPTools,
    LEARN_MCP_SERVER,
)
from src.services.mcp_client import MCPServerConfig, MCPToolResult, MCPTransportType


def _make_mock_manager(tool_result: MCPToolResult | None = None) -> MagicMock:
    """Create a mock MCPClientManager."""
    manager = MagicMock()
    manager._servers = {
        LEARN_MCP_SERVER: MCPServerConfig(
            name=LEARN_MCP_SERVER,
            transport_type=MCPTransportType.STREAMABLE_HTTP,
            endpoint="https://learn.microsoft.com/api/mcp",
        )
    }
    if tool_result:
        manager.call_tool = AsyncMock(return_value=tool_result)
    else:
        manager.call_tool = AsyncMock(return_value=MCPToolResult(available=False))
    return manager


class TestLearnMCPTools:
    async def test_search_docs_returns_results(self):
        result = MCPToolResult(
            available=True,
            data={"content": [
                {"title": "Azure Functions overview", "url": "https://learn.microsoft.com/azure/functions", "text": "Overview of serverless"},
                {"title": "Quickstart: Functions", "url": "https://learn.microsoft.com/azure/functions/quickstart", "text": "Get started fast"},
            ]},
            server=LEARN_MCP_SERVER,
            tool="microsoft_docs_search",
        )
        tools = LearnMCPTools(_make_mock_manager(result))
        results = await tools.search_docs("azure functions")
        assert len(results) == 2
        assert results[0].title == "Azure Functions overview"

    async def test_search_docs_unavailable(self):
        tools = LearnMCPTools(_make_mock_manager())
        results = await tools.search_docs("anything")
        assert results == []

    async def test_fetch_doc_returns_content(self):
        result = MCPToolResult(
            available=True,
            data={"content": "# Azure Functions\n\nServerless compute service...", "title": "Azure Functions"},
            server=LEARN_MCP_SERVER,
            tool="microsoft_docs_fetch",
        )
        tools = LearnMCPTools(_make_mock_manager(result))
        doc = await tools.fetch_doc("https://learn.microsoft.com/azure/functions")
        assert "Azure Functions" in doc.content
        assert doc.title == "Azure Functions"

    async def test_fetch_doc_truncates_long_content(self):
        long_content = "x" * 20000
        result = MCPToolResult(
            available=True,
            data={"content": long_content},
            server=LEARN_MCP_SERVER,
            tool="microsoft_docs_fetch",
        )
        tools = LearnMCPTools(_make_mock_manager(result), max_fetch_chars=1000)
        doc = await tools.fetch_doc("https://example.com")
        assert doc.truncated
        assert len(doc.content) < 20000

    async def test_fetch_doc_unavailable(self):
        tools = LearnMCPTools(_make_mock_manager())
        doc = await tools.fetch_doc("https://example.com")
        assert doc.content == ""

    async def test_search_code_samples(self):
        result = MCPToolResult(
            available=True,
            data={"content": [{"title": "HTTP trigger", "language": "python", "code": "import azure.functions"}]},
            server=LEARN_MCP_SERVER,
            tool="microsoft_code_sample_search",
        )
        tools = LearnMCPTools(_make_mock_manager(result))
        samples = await tools.search_code_samples("azure functions http trigger", language="python")
        assert len(samples) == 1
        assert samples[0].language == "python"

    async def test_available_property(self):
        tools = LearnMCPTools(_make_mock_manager())
        assert tools.available

    async def test_available_false_when_server_missing(self):
        manager = MagicMock()
        manager._servers = {}
        tools = LearnMCPTools(manager)
        assert not tools.available

    async def test_search_with_text_response(self):
        """Test handling when MCP returns plain text instead of structured data."""
        result = MCPToolResult(
            available=True,
            data={"text": "Azure Functions is a serverless compute service..."},
            server=LEARN_MCP_SERVER,
            tool="microsoft_docs_search",
        )
        tools = LearnMCPTools(_make_mock_manager(result))
        results = await tools.search_docs("azure functions")
        assert len(results) == 1
