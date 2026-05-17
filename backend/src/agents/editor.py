"""Editor Agent — refines generated documents for MS Learn style compliance."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog
from agent_framework import Agent

from src.utils.paths import get_prompts_dir

if TYPE_CHECKING:
    from agent_framework.foundry import FoundryChatClient

    from src.models.document import GeneratedDocument
    from src.services.learn_mcp_tools import LearnMCPTools

logger = structlog.get_logger()


class EditorAgent:
    """Reviews and refines documents for MS Learn voice, tone, and formatting compliance."""

    def __init__(self, client: FoundryChatClient, learn_tools: LearnMCPTools | None = None) -> None:
        self._client = client
        self._learn_tools = learn_tools
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = get_prompts_dir() / "editor_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a Microsoft Learn documentation editor."
            logger.warning("editor.prompt_not_found", path=str(prompt_path))

    def _extract_markdown(self, text: str) -> str:
        """Extract Markdown from LLM response, stripping code fences and trailing JSON."""
        # Try explicit ```markdown or ```md fences
        match = re.search(r'```(?:markdown|md)\s*\n(.*?)```', text, re.DOTALL)
        if match and match.group(1).strip():
            return match.group(1).strip()

        # Strip any outer code fence wrapper (```yaml, ```text, bare ```, etc.)
        outer = re.match(r'^```\w*\s*\n(.*)\n```\s*$', text.strip(), re.DOTALL)
        if outer and outer.group(1).strip():
            return outer.group(1).strip()

        cleaned = text.strip()

        # Strip trailing JSON block only when it matches the editor edit-summary shape
        cleaned = re.sub(
            r'\n```json\s*\n\{[^}]*"changes"[^}]*"total_changes"[^}]*\}\s*```\s*$',
            '',
            cleaned,
            flags=re.DOTALL,
        )
        # Also handle bare JSON (no code fence) at the end
        cleaned = re.sub(r'\n\{[\s\S]*"changes"[\s\S]*"total_changes"[\s\S]*\}\s*$', '', cleaned)

        return cleaned.strip()

    def _count_words(self, text: str) -> int:
        """Count words, excluding YAML frontmatter."""
        content = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
        return len(content.split())

    async def _fetch_style_reference(self, document: GeneratedDocument) -> str:
        """Fetch a published MS Learn article in the same topic for style comparison."""
        if not self._learn_tools or not self._learn_tools.available:
            return ""

        topic = document.outline.frontmatter.title or document.outline.frontmatter.ms_service
        if not topic:
            return ""

        try:
            results = await self._learn_tools.search_docs(topic, top_k=1)
            if not results or not results[0].url:
                return ""

            doc = await self._learn_tools.fetch_doc(results[0].url)
            if not doc.content:
                return ""

            logger.info(
                "editor.mcp_style_reference_fetched",
                doc_id=document.document_id,
                reference_url=results[0].url,
            )
            return (
                f"## Published MS Learn reference (use for style consistency)\n\n"
                f"Title: {doc.title or results[0].title}\n"
                f"URL: {results[0].url}\n\n"
                f"{doc.content}\n"
            )
        except Exception as exc:
            logger.warning(
                "editor.mcp_style_reference_failed",
                doc_id=document.document_id,
                error=str(exc),
            )
            return ""

    async def process(
        self, document: GeneratedDocument, feedback: str | None = None
    ) -> GeneratedDocument:
        """Review and refine a generated document.

        Args:
            document: The generated document to refine.
            feedback: Optional evaluation feedback for targeted revision.

        Returns:
            Refined GeneratedDocument with updated content, or the original if
            refinement fails validation.
        """
        logger.info("editor.start", doc_id=document.document_id, has_feedback=feedback is not None)

        # Fetch a published reference article for style comparison
        style_reference = await self._fetch_style_reference(document)

        user_message_parts = [
            document.markdown_content,
            "",
            "Review and refine this MS Learn article. Return the complete refined Markdown. Do not omit any sections.",
        ]
        if feedback:
            user_message_parts.insert(1, f"Evaluation feedback to address:\n{feedback}\n")
        if style_reference:
            user_message_parts.insert(1, style_reference)
        user_message = "\n".join(user_message_parts)

        response_text: str | None = None
        try:
            agent = Agent(
                client=self._client,
                name="EditorAgent",
                instructions=self._system_prompt,
            )
            result = await agent.run(user_message)
            response_text = result.text
        except Exception as exc:
            logger.warning(
                "editor.maf_fallback",
                doc_id=document.document_id,
                error=str(exc),
            )
            try:
                from agent_framework import Message

                messages = [
                    Message(role="system", contents=[self._system_prompt]),
                    Message(role="user", contents=[user_message]),
                ]
                response = await self._client.get_response(messages)
                response_text = response.text
            except Exception as inner_exc:
                logger.error(
                    "editor.llm_failed",
                    doc_id=document.document_id,
                    error=str(inner_exc),
                )
                return document

        if not response_text:
            logger.warning("editor.empty_response", doc_id=document.document_id)
            return document

        refined_markdown = self._extract_markdown(response_text)

        if not refined_markdown:
            logger.warning(
                "editor.empty_after_extraction",
                doc_id=document.document_id,
                response_len=len(response_text),
                response_preview=response_text[:200],
            )
            return document

        original_word_count = self._count_words(document.markdown_content)
        refined_word_count = self._count_words(refined_markdown)

        if original_word_count > 0 and refined_word_count < original_word_count * 0.5:
            logger.warning(
                "editor.truncation_detected",
                doc_id=document.document_id,
                original_words=original_word_count,
                refined_words=refined_word_count,
            )
            return document

        new_revision = document.revision_number + 1
        refined_document = document.model_copy(
            update={
                "markdown_content": refined_markdown,
                "revision_number": new_revision,
                "word_count": refined_word_count,
            }
        )

        logger.info(
            "editor.complete",
            doc_id=document.document_id,
            revision=new_revision,
            original_words=original_word_count,
            refined_words=refined_word_count,
        )
        return refined_document
