"""Work IQ MCP tool wrappers for M365 context enrichment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.services.mcp_client import MCPClientManager

logger = structlog.get_logger()

WORKIQ_MCP_SERVER = "workiq"


class M365Document(BaseModel):
    """A document found via Work IQ M365 search."""

    title: str = ""
    content_preview: str = Field(default="", description="Preview/summary of document content")
    url: str = ""
    source_type: str = Field(default="", description="Source type: document, email, meeting, teams_message")


class M365SearchResult(BaseModel):
    """Result of an M365 context search."""

    documents: list[M365Document] = Field(default_factory=list)
    summary: str = Field(default="", description="AI-generated summary of found context")
    query: str = ""
    available: bool = True


class WorkIQTools:
    """Wraps Work IQ MCP Server for M365 context enrichment.

    All queries are permission-gated — they must be explicitly triggered
    by the user, never called automatically by the pipeline.
    """

    def __init__(self, mcp_manager: MCPClientManager) -> None:
        self._mcp = mcp_manager

    @property
    def available(self) -> bool:
        """Check if Work IQ MCP server is configured and enabled."""
        return (
            WORKIQ_MCP_SERVER in self._mcp._servers
            and self._mcp._servers[WORKIQ_MCP_SERVER].enabled
        )

    async def search_context(self, query: str) -> M365SearchResult:
        """Search M365 for relevant context (documents, emails, meetings, Teams).

        This performs a broad search across all M365 data types.
        Must only be called when explicitly requested by the user.
        """
        logger.info("workiq.search_context", query_length=len(query))

        # Work IQ uses the "ask" tool — the primary interface
        result = await self._mcp.call_tool(
            WORKIQ_MCP_SERVER, "ask", {"question": query}
        )

        if not result.available or result.data is None:
            logger.warning("workiq.search_unavailable", query_length=len(query))
            return M365SearchResult(query=query, available=False)

        return self._parse_search_result(result.data, query)

    async def search_documents(self, query: str) -> list[M365Document]:
        """Search specifically for M365 documents related to a query.

        Convenience method that wraps search_context with a document-focused query.
        """
        doc_query = f"Find documents related to: {query}"
        result = await self.search_context(doc_query)
        return result.documents

    def _parse_search_result(self, data: dict[str, Any], query: str) -> M365SearchResult:
        """Parse Work IQ MCP response into M365SearchResult."""
        documents = []
        summary = ""

        # Work IQ returns content in MCP format
        content = data.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    # Work IQ responses are typically text summaries
                    if text:
                        summary += text + "\n"
                elif isinstance(item, str):
                    summary += item + "\n"
        elif isinstance(content, str):
            summary = content

        # Also handle top-level text field
        if not summary and "text" in data:
            summary = str(data["text"])

        # Try to extract document references from the summary.
        # Work IQ often includes document titles and URLs in its responses.
        if summary:
            documents.append(M365Document(
                title="M365 Context",
                content_preview=summary[:2000],
                source_type="mixed",
            ))

        logger.info(
            "workiq.search_complete",
            query=query,
            doc_count=len(documents),
            summary_length=len(summary),
        )

        return M365SearchResult(
            documents=documents,
            summary=summary.strip(),
            query=query,
            available=True,
        )
