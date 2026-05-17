"""Microsoft Learn MCP tool wrappers for documentation grounding."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.services.mcp_client import MCPClientManager

logger = structlog.get_logger()

# Server name used in MCPClientManager
LEARN_MCP_SERVER = "microsoft_learn"

# Max tokens for fetched content (rough char estimate: 1 token ≈ 4 chars)
DEFAULT_FETCH_MAX_CHARS = 8000


class DocSearchResult(BaseModel):
    """A search result from Microsoft Learn."""

    title: str = ""
    url: str = ""
    description: str = ""
    relevance_score: float = 0.0


class DocContent(BaseModel):
    """Fetched content from a Microsoft Learn article."""

    url: str = ""
    title: str = ""
    content: str = Field(default="", description="Article content (may be truncated to token budget)")
    truncated: bool = False


class CodeSample(BaseModel):
    """A code sample from Microsoft Learn."""

    title: str = ""
    url: str = ""
    language: str = ""
    code: str = ""


class LearnMCPTools:
    """Wraps Microsoft Learn MCP Server tools for agent use."""

    def __init__(self, mcp_manager: MCPClientManager, max_fetch_chars: int = DEFAULT_FETCH_MAX_CHARS) -> None:
        self._mcp = mcp_manager
        self._max_fetch_chars = max_fetch_chars

    @property
    def available(self) -> bool:
        """Check if the Learn MCP server config is present and enabled."""
        return LEARN_MCP_SERVER in self._mcp._servers and self._mcp._servers[LEARN_MCP_SERVER].enabled

    async def search_docs(self, query: str, top_k: int = 5) -> list[DocSearchResult]:
        """Search Microsoft Learn for related articles."""
        result = await self._mcp.call_tool(
            LEARN_MCP_SERVER, "microsoft_docs_search", {"query": query}
        )
        if not result.available or not result.data:
            logger.debug("learn_mcp.search_unavailable", query=query)
            return []

        return self._parse_search_results(result.data, top_k)

    async def fetch_doc(self, url: str) -> DocContent:
        """Fetch the full content of a Microsoft Learn article."""
        result = await self._mcp.call_tool(
            LEARN_MCP_SERVER, "microsoft_docs_fetch", {"url": url}
        )
        if not result.available or not result.data:
            logger.debug("learn_mcp.fetch_unavailable", url=url)
            return DocContent(url=url)

        return self._parse_doc_content(result.data, url)

    async def search_code_samples(self, query: str, language: str = "") -> list[CodeSample]:
        """Search for official code samples in Microsoft Learn."""
        params: dict[str, Any] = {"query": query}
        if language:
            params["language"] = language

        result = await self._mcp.call_tool(
            LEARN_MCP_SERVER, "microsoft_code_sample_search", params
        )
        if not result.available or not result.data:
            logger.debug("learn_mcp.code_search_unavailable", query=query)
            return []

        return self._parse_code_samples(result.data)

    def _parse_search_results(self, data: dict[str, Any], top_k: int) -> list[DocSearchResult]:
        """Parse MCP search results into DocSearchResult models."""
        results = []
        # The MCP tool returns content which may be a list of results or a text block
        # Handle both structured and text responses
        content = data.get("content", [])
        if isinstance(content, list):
            for item in content[:top_k]:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    results.append(DocSearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        description=text[:500] if text else "",
                    ))
                elif isinstance(item, str):
                    results.append(DocSearchResult(description=item[:500]))
        elif isinstance(content, str):
            # Single text block — treat as one result
            results.append(DocSearchResult(description=content[:500]))

        # Also check for a "text" field at the top level (common MCP response format)
        if not results and "text" in data:
            results.append(DocSearchResult(description=str(data["text"])[:500]))

        logger.info("learn_mcp.search_results", count=len(results))
        return results[:top_k]

    def _parse_doc_content(self, data: dict[str, Any], url: str) -> DocContent:
        """Parse MCP fetch result into DocContent with truncation."""
        content = ""
        if isinstance(data.get("content"), list):
            parts = []
            for item in data["content"]:
                if isinstance(item, dict):
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            content = "\n".join(parts)
        elif isinstance(data.get("content"), str):
            content = data["content"]
        elif "text" in data:
            content = str(data["text"])

        truncated = len(content) > self._max_fetch_chars
        if truncated:
            content = content[:self._max_fetch_chars] + "\n\n[Content truncated for token budget]"

        return DocContent(
            url=url,
            title=data.get("title", ""),
            content=content,
            truncated=truncated,
        )

    def _parse_code_samples(self, data: dict[str, Any]) -> list[CodeSample]:
        """Parse MCP code sample search results."""
        samples = []
        content = data.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    samples.append(CodeSample(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        language=item.get("language", ""),
                        code=item.get("code", item.get("text", "")),
                    ))

        if not samples and "text" in data:
            samples.append(CodeSample(code=str(data["text"])[:2000]))

        logger.info("learn_mcp.code_samples", count=len(samples))
        return samples
