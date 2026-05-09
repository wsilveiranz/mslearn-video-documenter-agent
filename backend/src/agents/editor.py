"""Editor Agent — refines generated documents for MS Learn style compliance."""

from __future__ import annotations

from pathlib import Path

import structlog

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from src.models.document import GeneratedDocument

logger = structlog.get_logger()


class EditorAgent:
    """Reviews and refines documents for MS Learn voice, tone, and formatting compliance."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "editor_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a Microsoft Learn documentation editor."
            logger.warning("editor.prompt_not_found", path=str(prompt_path))

    async def process(
        self, document: GeneratedDocument, feedback: str | None = None
    ) -> GeneratedDocument:
        """Review and refine a generated document.
        
        Args:
            document: The generated document to refine.
            feedback: Optional user feedback for targeted revision.
            
        Returns:
            Refined GeneratedDocument with updated content.
        """
        logger.info("editor.start", doc_id=document.document_id, has_feedback=feedback is not None)

        # TODO Phase 1: Use MAF Agent to review and refine
        # - Send document + editor system prompt
        # - If feedback provided, include as additional context
        # - Parse refined Markdown output
        # - Increment revision number

        agent = Agent(
            client=self._client,
            name="EditorAgent",
            instructions=self._system_prompt,
        )

        # Placeholder: return document unchanged
        logger.info("editor.complete", doc_id=document.document_id, revision=document.revision_number)
        return document
