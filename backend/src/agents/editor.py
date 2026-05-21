"""Editor Agent — refines generated documents for MS Learn style compliance."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog
from agent_framework import Agent

from src.utils.paths import get_prompts_dir

if TYPE_CHECKING:
    from agent_framework.foundry import FoundryChatClient

    from src.models.document import GeneratedDocument, Screenshot
    from src.models.video import ExtractionResult
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

    def _build_keyframe_catalog(
        self, document: GeneratedDocument, extraction: ExtractionResult | None
    ) -> str:
        """Build a keyframe catalog so the editor can reassign screenshots.

        Lists all available keyframes with descriptions and the current
        screenshot assignments, so the editor knows what alternatives exist.
        """
        if not extraction or not extraction.keyframes:
            return ""

        lines = [
            "## Available keyframes (screenshot catalog)\n",
            "You CAN reassign, reorder, or swap :::image::: references. "
            "Use the keyframe ID in the output_path when reassigning. "
            "Each keyframe below shows its timestamp, scene, and visual description.\n",
            "### All available keyframes\n",
        ]

        for kf in extraction.keyframes:
            desc = kf.ui_description or "(no description)"
            scene = f"scene {kf.scene_id}" if kf.scene_id else "no scene"
            lines.append(f"- **{kf.id}** [{kf.timestamp_seconds:.1f}s, {scene}]: {desc}")

        # Show current assignments
        if document.media_files:
            lines.append("\n### Current screenshot assignments\n")
            for s in document.media_files:
                lines.append(f"- `{s.output_path}` (keyframe {s.keyframe_id}) — {s.alt_text}")

        lines.append(
            "\n### Instructions for screenshot changes\n"
            "If the user requests screenshot changes, update the :::image::: references "
            "in the Markdown to use different keyframes. Change the alt-text to match "
            "the new keyframe's description. Use descriptive output_path names.\n"
        )

        return "\n".join(lines)

    def _sync_media_files(
        self, markdown: str, document: GeneratedDocument, extraction: ExtractionResult | None
    ) -> list[Screenshot]:
        """Sync the media_files list with :::image::: references in the edited markdown.

        If the editor changed image references, update the screenshot list accordingly.
        """
        from src.models.document import Screenshot

        # Extract all :::image::: source paths from the markdown
        image_pattern = re.compile(r':::image\s+type="content"\s+source="([^"]+)"\s+alt-text="([^"]*)"')
        referenced = [(m.group(1), m.group(2)) for m in image_pattern.finditer(markdown)]

        if not referenced:
            return document.media_files

        # Build lookup from output_path → existing screenshot
        existing = {s.output_path: s for s in document.media_files}

        # Build lookup from keyframe_id → keyframe (for reassignment)
        kf_map = {}
        if extraction:
            kf_map = {kf.id: kf for kf in extraction.keyframes}

        updated: list[Screenshot] = []
        for idx, (src_path, alt_text) in enumerate(referenced):
            if src_path in existing:
                # Existing screenshot — keep it (alt-text may have been updated)
                s = existing[src_path]
                if alt_text and alt_text != s.alt_text:
                    s = s.model_copy(update={"alt_text": alt_text})
                updated.append(s)
            else:
                # New path — try to match a keyframe by ID in the path or by description
                matched_kf = None
                for kf_id, kf in kf_map.items():
                    if kf_id in src_path:
                        matched_kf = kf
                        break

                if matched_kf:
                    updated.append(Screenshot(
                        keyframe_id=matched_kf.id,
                        source_path=matched_kf.image_path,
                        output_path=src_path,
                        alt_text=alt_text or matched_kf.ui_description or f"Screenshot {idx + 1}",
                        step_number=idx + 1,
                    ))
                else:
                    # Keep the reference even if we can't match a keyframe
                    updated.append(Screenshot(
                        keyframe_id=f"unknown-{idx}",
                        source_path="",
                        output_path=src_path,
                        alt_text=alt_text or f"Screenshot {idx + 1}",
                        step_number=idx + 1,
                    ))

        if updated:
            logger.info(
                "editor.media_synced",
                doc_id=document.document_id,
                original_count=len(document.media_files),
                updated_count=len(updated),
            )

        return updated

    async def process(
        self, document: GeneratedDocument, feedback: str | None = None,
        extraction: ExtractionResult | None = None,
        reference_files: list[dict[str, str]] | None = None,
    ) -> GeneratedDocument:
        """Review and refine a generated document.

        Args:
            document: The generated document to refine.
            feedback: Optional evaluation feedback for targeted revision.
            extraction: Optional extraction data — provides keyframe catalog for screenshot reassignment.
            reference_files: Optional reference files to use as examples for requested edits.

        Returns:
            Refined GeneratedDocument with updated content, or the original if
            refinement fails validation.
        """
        logger.info(
            "editor.start",
            doc_id=document.document_id,
            has_feedback=feedback is not None,
            ref_files=len(reference_files or []),
        )

        # Fetch a published reference article for style comparison
        style_reference = await self._fetch_style_reference(document)

        # Build keyframe catalog so the editor can reassign screenshots
        keyframe_catalog = self._build_keyframe_catalog(document, extraction)

        user_message_parts = [
            document.markdown_content,
            "",
            "Review and refine this MS Learn article. Return the complete refined Markdown. Do not omit any sections.",
        ]
        if feedback:
            user_message_parts.insert(1, f"User feedback to address:\n{feedback}\n")
        if reference_files:
            ref_block_parts = ["## Reference Files (use as examples for the requested edits)\n"]
            for rf in reference_files:
                ref_block_parts.append(f"### --- {rf['filename']} ---\n{rf['content']}\n")
            ref_block = "\n".join(ref_block_parts)
            user_message_parts.insert(1, ref_block)
        if keyframe_catalog:
            user_message_parts.insert(1, keyframe_catalog)
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

        # Sync media_files with any :::image::: changes the editor made
        updated_media = self._sync_media_files(refined_markdown, document, extraction)

        refined_document = document.model_copy(
            update={
                "markdown_content": refined_markdown,
                "revision_number": new_revision,
                "word_count": refined_word_count,
                "media_files": updated_media,
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
