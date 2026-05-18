"""Writer Agent — generates full MS Learn Markdown from a document outline."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

import structlog
from agent_framework import Agent

from src.models.document import DocType, DocumentOutline, GeneratedDocument, Screenshot
from src.utils.paths import get_prompts_dir, get_templates_dir

if TYPE_CHECKING:
    from agent_framework.foundry import FoundryChatClient

    from src.models.video import DataQualityReport, ExtractionResult
    from src.services.learn_mcp_tools import LearnMCPTools

logger = structlog.get_logger()


class WriterAgent:
    """Generates MS Learn-style Markdown documents from structured outlines."""

    def __init__(self, client: FoundryChatClient, learn_tools: LearnMCPTools | None = None) -> None:
        self._client = client
        self._learn_tools = learn_tools
        self._load_system_prompt()
        self._load_template_cache()

    def _load_system_prompt(self) -> None:
        prompt_path = get_prompts_dir() / "writer_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a Microsoft Learn documentation writer."
            logger.warning("writer.prompt_not_found", path=str(prompt_path))

    def _load_template_cache(self) -> None:
        """Pre-load MS Learn templates."""
        self._templates: dict[DocType, str] = {}
        templates_dir = get_templates_dir()
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
        self, outline: DocumentOutline, extraction: ExtractionResult,
        quality_report: DataQualityReport | None = None,
        supplementary_context: str = "",
    ) -> GeneratedDocument:
        """Generate a full Markdown document from the outline.

        Args:
            outline: Document structure with sections and screenshots.
            extraction: Original extraction data for reference.
            quality_report: Optional quality assessment; injects guardrails when thin/minimal.
            supplementary_context: Reference docs and additional context from user.

        Returns:
            GeneratedDocument with full Markdown content.
        """
        logger.info(
            "writer.start",
            doc_type=outline.doc_type,
            sections=len(outline.sections),
            quality_level=quality_report.quality_level if quality_report else "unknown",
        )

        # Fetch MS Learn grounding context (voice/tone examples + code samples)
        mcp_grounding = await self._fetch_mcp_grounding(outline, extraction)

        template = self._templates.get(outline.doc_type, "")
        outline_json = outline.model_dump_json(indent=2)
        extraction_context = self._build_extraction_context(extraction)

        quality_guardrail = ""
        if quality_report and quality_report.quality_level in ("thin", "minimal"):
            gaps = (
                "\n".join(f"- {gap}" for gap in quality_report.coverage_gaps)
                if quality_report.coverage_gaps
                else "- No specific gaps identified"
            )
            confidence = f"{quality_report.grounding_confidence:.0%}"
            quality_guardrail = (
                "## ⚠️ THIN DATA GUARDRAIL — READ CAREFULLY\n\n"
                f"**Data quality: {quality_report.quality_level}** "
                f"(grounding confidence: {confidence})\n\n"
                "The extraction data for this video is insufficient "
                "for fully grounded documentation. "
                "You MUST follow these rules:\n\n"
                "1. **DO NOT fabricate steps, commands, UI paths, or "
                "procedures** not evidenced in the extraction data.\n"
                "2. For any section where extraction data is insufficient, insert a visible TODO comment:\n"
                "   `<!-- TODO: Verify — not shown in video -->`\n"
                "3. **Prefer shorter, conservative output** over comprehensive but ungrounded content.\n"
                "4. Add this alert after the introduction:\n"
                "   ```\n"
                "   > [!IMPORTANT]\n"
                "   > This article was generated from a video with limited extraction data. "
                "Some sections may be incomplete or require verification.\n"
                "   ```\n"
                "5. **Coverage gaps identified by quality assessment:**\n"
                f"{gaps}\n\n"
            )

        screenshot_manifest = ""
        if outline.screenshots:
            manifest_lines = [
                "## Screenshot Manifest\n",
                "Use these EXACT paths for :::image::: references:\n",
            ]
            for s in outline.screenshots:
                manifest_lines.append(f"- `{s.output_path}` — {s.alt_text}")
            screenshot_manifest = "\n".join(manifest_lines) + "\n\n"

        supplementary_section = ""
        if supplementary_context:
            # Truncate to avoid token overflow (keep most relevant content at the top)
            max_context = 12000
            ctx = supplementary_context[:max_context]
            if len(supplementary_context) > max_context:
                ctx += "\n\n[… truncated for length]"
            supplementary_section = (
                "## Reference documents (REQUIRED — primary source material)\n\n"
                "These documents are authoritative source material provided by the user. "
                "You MUST actively integrate information from these documents into the article:\n\n"
                "- Use them to fill prerequisites, configuration values, and setup details\n"
                "- Use correct terminology and naming from these documents\n"
                "- Replace TODO placeholders with real content where these documents provide the answer\n"
                "- Add detail to procedures that the video mentions but doesn't elaborate on\n"
                "- Include limitations, known issues, or constraints documented here\n\n"
                "Treat these documents as EQUAL in authority to the video transcript. "
                "Content from reference documents is grounded (not hallucinated) — use it confidently.\n\n"
                f"{ctx}\n\n"
            )

        user_message = (
            quality_guardrail +
            "## Document Outline\n\n"
            f"```json\n{outline_json}\n```\n\n"
            "## MS Learn Template\n\n"
            f"{template}\n\n"
            "## Extraction Data\n\n"
            f"{extraction_context}\n\n"
            f"{screenshot_manifest}"
            f"{supplementary_section}"
            f"{mcp_grounding}"
            "## Instructions\n\n"
            "Generate a complete MS Learn article following the outline and template. "
            "Include YAML frontmatter, all sections, numbered steps, and :::image::: references for screenshots. "
            "Use the extraction data to ground your content — do not invent steps not shown in the video. "
            "Reference documents are a PRIMARY source — actively weave their content into every relevant section. "
            "If a reference doc provides details the video skips (config values, prerequisites, limitations, exact commands), "
            "include them as real content, not TODOs. "
            "Return the complete Markdown document only, without any explanation or wrapper text."
        )

        agent = Agent(
            client=self._client,
            name="WriterAgent",
            instructions=self._system_prompt,
        )

        markdown_content = await self._generate_with_retry(agent, user_message, outline, template, outline_json)
        markdown_content = self._normalize_image_paths(markdown_content, outline.screenshots)

        doc_id = uuid.uuid4().hex[:12]
        word_count = self._count_words(markdown_content)

        document = GeneratedDocument(
            document_id=doc_id,
            doc_type=outline.doc_type,
            outline=outline,
            markdown_content=markdown_content,
            media_files=outline.screenshots,
            word_count=word_count,
            revision_number=1,
        )

        logger.info("writer.complete", doc_id=doc_id, words=word_count, doc_type=outline.doc_type)
        return document

    async def _fetch_mcp_grounding(self, outline: DocumentOutline, extraction: ExtractionResult) -> str:
        """Fetch published MS Learn articles and code samples for voice/tone grounding."""
        if not self._learn_tools or not self._learn_tools.available:
            return ""

        topic = outline.frontmatter.title or outline.frontmatter.ms_service
        if not topic:
            return ""

        grounding_parts: list[str] = []

        try:
            # Fetch 1-2 published articles as voice/tone reference
            search_results = await self._learn_tools.search_docs(topic, top_k=2)
            fetched_articles: list[str] = []
            for result in search_results[:2]:
                if result.url:
                    doc = await self._learn_tools.fetch_doc(result.url)
                    if doc.content:
                        fetched_articles.append(
                            f"### Reference: {doc.title or result.title}\n\n{doc.content}"
                        )
            if fetched_articles:
                grounding_parts.append(
                    "## MS Learn Voice/Tone Reference (published articles)\n\n"
                    "Use these published articles as a reference for voice, tone, and formatting style:\n\n"
                    + "\n\n---\n\n".join(fetched_articles)
                    + "\n\n"
                )
                logger.info("writer.mcp_articles_fetched", topic=topic, count=len(fetched_articles))
        except Exception as exc:
            logger.warning("writer.mcp_articles_failed", topic=topic, error=str(exc))

        # Search for code samples if the content involves code (OCR or transcript hints)
        has_code = bool(extraction.ocr_entries) or any(
            kw in " ".join(seg.text for seg in extraction.transcript).lower()
            for kw in ("code", "command", "script", "function", "api", "cli")
        )
        if has_code:
            try:
                code_samples = await self._learn_tools.search_code_samples(topic)
                if code_samples:
                    sample_lines = []
                    for sample in code_samples[:3]:
                        lang = sample.language or ""
                        fence = f"```{lang}" if lang else "```"
                        sample_lines.append(f"**{sample.title}**\n\n{fence}\n{sample.code}\n```")
                    grounding_parts.append(
                        "## Official Code Samples (from Microsoft Learn)\n\n"
                        + "\n\n".join(sample_lines)
                        + "\n\n"
                    )
                    logger.info("writer.mcp_code_samples_fetched", topic=topic, count=len(code_samples))
            except Exception as exc:
                logger.warning("writer.mcp_code_samples_failed", topic=topic, error=str(exc))

        return "".join(grounding_parts)

    async def _generate_with_retry(
        self,
        agent: Agent,
        user_message: str,
        outline: DocumentOutline,
        template: str,
        outline_json: str,
    ) -> str:
        """Call the LLM, retrying once with shorter context if needed."""
        markdown_content = await self._call_agent(agent, user_message)

        if not markdown_content or len(markdown_content) < 100:
            logger.warning("writer.empty_response", operation="retry_generation")
            short_message = self._build_short_user_message(outline, template, outline_json)
            markdown_content = await self._call_agent(agent, short_message)

        if not markdown_content or len(markdown_content) < 100:
            logger.warning("writer.using_fallback", operation="fallback_generation")
            markdown_content = self._outline_to_markdown(outline)

        return markdown_content

    async def _call_agent(self, agent: Agent, user_message: str) -> str:
        """Invoke the MAF agent and return extracted Markdown, or empty string on error."""
        try:
            result = await agent.run(user_message)
            response_text = result.text
            return self._extract_markdown(response_text)
        except Exception as exc:
            logger.warning("writer.llm_error", error=str(exc), operation="llm_call")
            return ""

    def _build_short_user_message(
        self, outline: DocumentOutline, template: str, outline_json: str
    ) -> str:
        """Build a reduced-context user message for the retry attempt."""
        excerpt_segments = outline.sections[:3] if outline.sections else []
        section_hints = "\n".join(f"- {s.heading}: {s.content_hint}" for s in excerpt_segments)
        return (
            "## Document Outline (summary)\n\n"
            f"```json\n{outline_json}\n```\n\n"
            "## MS Learn Template\n\n"
            f"{template}\n\n"
            "## Key sections\n\n"
            f"{section_hints}\n\n"
            "## Instructions\n\n"
            "Generate a complete MS Learn article following the outline and template. "
            "Include YAML frontmatter, all sections, numbered steps, and :::image::: references for screenshots. "
            "Return the complete Markdown document only."
        )

    def _outline_to_markdown(self, outline: DocumentOutline) -> str:
        """Produce a minimal Markdown skeleton from the outline as a last-resort fallback."""
        fm = outline.frontmatter
        lines: list[str] = [
            "---",
            f'title: "{fm.title}"',
            f'description: "{fm.description}"',
            f"author: {fm.author}",
            f"ms.author: {fm.ms_author}",
            f"ms.date: {fm.ms_date}",
            f"ms.topic: {fm.ms_topic}",
            f"ms.service: {fm.ms_service}",
            "ms.custom: ai-assisted",
            f"# Customer intent: {fm.customer_intent}",
            "---",
            "",
        ]
        for section in outline.sections:
            prefix = "#" * section.level
            lines.append(f"{prefix} {section.heading}")
            lines.append("")
            if section.content_hint:
                lines.append(f"<!-- {section.content_hint} -->")
                lines.append("")
            for step in section.steps:
                lines.append(f"1. {step}")
            if section.steps:
                lines.append("")
            for screenshot in section.screenshots:
                lines.append(
                    f':::image type="content" source="{screenshot.output_path or screenshot.source_path}"'
                    f' alt-text="{screenshot.alt_text}":::'
                )
                lines.append("")
        return "\n".join(lines)

    def _normalize_image_paths(self, markdown: str, screenshots: list[Screenshot]) -> str:
        """Replace any :::image source paths with the correct output_path from the screenshot manifest.

        Matches images by alt-text to avoid positional coupling — if the LLM
        reorders or omits screenshots, paths are still assigned correctly.
        Falls back to positional matching only when alt-text lookup fails.
        """
        if not screenshots:
            return markdown

        # Build alt-text → output_path lookup (case-insensitive, stripped)
        alt_to_path: dict[str, str] = {}
        for s in screenshots:
            if s.output_path and s.alt_text:
                alt_to_path[s.alt_text.strip().lower()] = s.output_path

        # Positional fallback list
        output_paths = [s.output_path for s in screenshots if s.output_path]
        if not output_paths and not alt_to_path:
            return markdown

        pattern = r'(:::image\s[^:]*?source=")([^"]*?)("\s[^:]*?alt-text=")([^"]*?)("[^:]*?:::)'
        matches = list(re.finditer(pattern, markdown))
        if not matches:
            # Try simpler pattern without alt-text capture for fallback
            simple_pattern = r'(:::image\s[^:]*?source=")([^"]*?)("[^:]*?:::)'
            matches = list(re.finditer(simple_pattern, markdown))
            if not matches:
                return markdown
            # Positional fallback only
            result = markdown
            for i, match in enumerate(reversed(matches)):
                idx = len(matches) - 1 - i
                if idx < len(output_paths):
                    result = result[:match.start(2)] + output_paths[idx] + result[match.end(2):]
            return result

        # Match by alt-text, fall back to positional index
        result = markdown
        positional_idx = 0
        for i, match in enumerate(reversed(matches)):
            idx = len(matches) - 1 - i
            alt_text = match.group(4).strip().lower()
            if alt_text in alt_to_path:
                new_path = alt_to_path[alt_text]
            elif positional_idx < len(output_paths):
                new_path = output_paths[positional_idx]
                positional_idx += 1
            else:
                continue
            result = result[:match.start(2)] + new_path + result[match.end(2):]

        return result

    def _build_extraction_context(self, extraction: ExtractionResult) -> str:
        """Build a text summary of extraction data for the LLM."""
        parts: list[str] = []

        if extraction.transcript:
            transcript_text = " ".join(seg.text for seg in extraction.transcript)
            parts.append(f"## Transcript\n{transcript_text}")

        if extraction.keyframes:
            kf_descriptions = "\n".join(
                f"- [{kf.id}] at {kf.timestamp_seconds:.1f}s: {kf.ui_description}"
                for kf in extraction.keyframes
                if kf.ui_description
            )
            if kf_descriptions:
                parts.append(f"## Keyframe Descriptions\n{kf_descriptions}")

        if extraction.ocr_entries:
            ocr_text = "\n".join(f"- {entry.text}" for entry in extraction.ocr_entries)
            parts.append(f"## On-Screen Text (OCR)\n{ocr_text}")

        return "\n\n".join(parts)

    def _extract_markdown(self, text: str) -> str:
        """Extract Markdown content from LLM response, stripping code fences if present."""
        # Try explicit ```markdown or ```md fences
        match = re.search(r"```(?:markdown|md)\s*\n(.*?)```", text, re.DOTALL)
        if match and match.group(1).strip():
            return match.group(1).strip()

        # Strip any outer code fence wrapper (```yaml, ```text, bare ```, etc.)
        outer = re.match(r"^```\w*\s*\n(.*)\n```\s*$", text.strip(), re.DOTALL)
        if outer and outer.group(1).strip():
            return outer.group(1).strip()

        return text.strip()

    def _count_words(self, text: str) -> int:
        """Count words in text, excluding YAML frontmatter."""
        content = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
        return len(content.split())
