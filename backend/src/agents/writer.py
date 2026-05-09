"""Writer Agent — generates full MS Learn Markdown from a document outline."""

from __future__ import annotations

from pathlib import Path

import structlog

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from src.models.document import DocType, DocumentOutline, GeneratedDocument
from src.models.video import ExtractionResult

logger = structlog.get_logger()


class WriterAgent:
    """Generates MS Learn-style Markdown documents from structured outlines."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._load_system_prompt()
        self._load_template_cache()

    def _load_system_prompt(self) -> None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "writer_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a Microsoft Learn documentation writer."
            logger.warning("writer.prompt_not_found", path=str(prompt_path))

    def _load_template_cache(self) -> None:
        """Pre-load MS Learn templates."""
        self._templates: dict[DocType, str] = {}
        templates_dir = Path(__file__).parent.parent / "templates"
        template_map = {
            DocType.QUICKSTART: "quickstart.md",
            DocType.TUTORIAL: "tutorial.md",
            DocType.HOWTO: "howto.md",
            DocType.CONCEPT: "concept.md",
            DocType.OVERVIEW: "overview.md",
        }
        for doc_type, filename in template_map.items():
            path = templates_dir / filename
            try:
                self._templates[doc_type] = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                logger.warning("writer.template_not_found", doc_type=doc_type, path=str(path))

    async def process(
        self, outline: DocumentOutline, extraction: ExtractionResult
    ) -> GeneratedDocument:
        """Generate a full Markdown document from the outline.
        
        Args:
            outline: Document structure with sections and screenshots.
            extraction: Original extraction data for reference.
            
        Returns:
            GeneratedDocument with full Markdown content.
        """
        logger.info("writer.start", doc_type=outline.doc_type, sections=len(outline.sections))

        # TODO Phase 1: Use MAF Agent to generate each section
        # - Build user prompt with outline + extraction context + template
        # - Stream LLM response
        # - Assemble final Markdown

        agent = Agent(
            client=self._client,
            name="WriterAgent",
            instructions=self._system_prompt,
        )

        template = self._templates.get(outline.doc_type, "")

        # Placeholder output
        document = GeneratedDocument(
            document_id="placeholder-doc-id",
            doc_type=outline.doc_type,
            outline=outline,
            markdown_content=f"# Placeholder {outline.doc_type.value}\n\nDocument generation coming in Phase 1.",
        )

        logger.info("writer.complete", doc_id=document.document_id, words=document.word_count)
        return document
