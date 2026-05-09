"""Structure Agent — maps extraction results to an MS Learn document outline."""

from __future__ import annotations

import structlog

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from src.models.document import DocType, DocumentOutline, Frontmatter
from src.models.video import ExtractionResult

logger = structlog.get_logger()


class StructureAgent:
    """Analyzes extraction results and creates a document outline matching an MS Learn template."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        """Load the structure agent system prompt from file."""
        from pathlib import Path

        prompt_path = Path(__file__).parent.parent / "prompts" / "structure_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a document structure analyzer for Microsoft Learn documentation."
            logger.warning("structure.prompt_not_found", path=str(prompt_path))

    async def process(
        self, extraction: ExtractionResult, doc_type: DocType, supplementary_context: str = ""
    ) -> DocumentOutline:
        """Create a document outline from extraction results.
        
        Args:
            extraction: Structured data extracted from the video.
            doc_type: The MS Learn document type to generate.
            supplementary_context: Additional context from user (README, API specs, etc.).
            
        Returns:
            DocumentOutline with sections, screenshots, and frontmatter skeleton.
        """
        logger.info("structure.start", doc_type=doc_type, scenes=len(extraction.scenes))

        # TODO Phase 1: Use the MAF Agent to analyze extraction and build outline
        # - Send extraction summary to LLM with structure_system prompt
        # - Parse LLM response into DocumentOutline
        # - Select best keyframe per section
        # - Generate section headings
        
        agent = Agent(
            client=self._client,
            name="StructureAgent",
            instructions=self._system_prompt,
        )

        # Placeholder outline
        outline = DocumentOutline(
            doc_type=doc_type,
            frontmatter=Frontmatter(
                title=f"Placeholder {doc_type.value} title",
                description=f"Placeholder description for {doc_type.value} article",
            ),
        )

        logger.info("structure.complete", sections=len(outline.sections))
        return outline
