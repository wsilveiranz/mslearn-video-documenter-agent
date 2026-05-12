"""Structure Agent — maps extraction results to an MS Learn document outline."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from agent_framework import Agent

from src.models.document import DocType, DocumentMetadata, DocumentOutline, DocumentSection, Frontmatter, Screenshot
from src.utils.paths import get_prompts_dir

if TYPE_CHECKING:
    from agent_framework.foundry import FoundryChatClient

    from src.models.video import ExtractionResult, Keyframe

logger = structlog.get_logger()

_MS_TOPIC_MAP: dict[DocType, str] = {
    DocType.QUICKSTART: "quickstart",
    DocType.TUTORIAL: "tutorial",
    DocType.HOWTO: "how-to",
    DocType.CONCEPT: "concept-article",
    DocType.OVERVIEW: "overview",
}


class StructureAgent:
    """Analyzes extraction results and creates a document outline matching an MS Learn template."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        """Load the structure agent system prompt from file."""
        prompt_path = get_prompts_dir() / "structure_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a document structure analyzer for Microsoft Learn documentation."
            logger.warning("structure.prompt_not_found", path=str(prompt_path))

    async def process(
        self,
        extraction: ExtractionResult,
        doc_type: DocType,
        supplementary_context: str = "",
        metadata: DocumentMetadata | None = None,
    ) -> DocumentOutline:
        """Create a document outline from extraction results.

        Args:
            extraction: Structured data extracted from the video.
            doc_type: The MS Learn document type to generate.
            supplementary_context: Additional context from user (README, API specs, etc.).
            metadata: Optional user-provided frontmatter values (author, ms_author, etc.).

        Returns:
            DocumentOutline with sections, screenshots, and frontmatter skeleton.
        """
        logger.info("structure.start", doc_type=doc_type, scenes=len(extraction.scenes))

        user_message = self._build_user_message(extraction, doc_type, supplementary_context, metadata)

        agent = Agent(
            client=self._client,
            name="StructureAgent",
            instructions=self._system_prompt,
        )

        response_text = await self._run_agent(agent, user_message)

        outline = self._parse_outline(response_text, extraction, doc_type, metadata)
        outline = self._attach_screenshots(outline, extraction)

        logger.info(
            "structure.complete",
            doc_type=doc_type,
            sections=len(outline.sections),
            screenshots=len(outline.screenshots),
        )
        return outline

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user_message(
        self,
        extraction: ExtractionResult,
        doc_type: DocType,
        supplementary_context: str,
        metadata: DocumentMetadata | None = None,
    ) -> str:
        """Build the user message summarising the extraction data for the LLM."""
        transcript_text = " ".join(seg.text for seg in extraction.transcript)

        scenes_summary = "\n".join(
            f"- Scene {s.id} [{s.start_seconds:.1f}s-{s.end_seconds:.1f}s]: {s.description}"
            for s in extraction.scenes
        )

        keyframes_summary = "\n".join(
            f"- Keyframe {kf.id} [{kf.timestamp_seconds:.1f}s] (scene {kf.scene_id}): {kf.ui_description}"
            for kf in extraction.keyframes
            if kf.ui_description
        )

        ocr_summary = "\n".join(
            f"- [{entry.timestamp_seconds:.1f}s] {entry.text}"
            for entry in extraction.ocr_entries[:50]  # cap to avoid token overflow
        )

        entities_summary = ", ".join(
            f"{e.name} ({e.entity_type})" for e in extraction.entities
        ) or "None detected"

        parts = [
            f"## Document type requested\n{doc_type.value}",
            f"## Video metadata\nDuration: {extraction.video_metadata.duration_seconds:.1f}s | "
            f"Resolution: {extraction.video_metadata.resolution_width}x{extraction.video_metadata.resolution_height}",
            f"## Full transcript\n{transcript_text or '(no transcript available)'}",
            f"## Scenes ({len(extraction.scenes)} detected)\n{scenes_summary or '(no scenes)'}",
            f"## Keyframes ({len(extraction.keyframes)} captured)\n{keyframes_summary or '(no keyframes)'}",
            f"## OCR text entries\n{ocr_summary or '(no OCR text)'}",
            f"## Entities detected\n{entities_summary}",
        ]

        if supplementary_context:
            parts.append(f"## Supplementary context\n{supplementary_context}")

        if metadata:
            meta_parts = []
            if metadata.author:
                meta_parts.append(f"- author: {metadata.author}")
            if metadata.ms_author:
                meta_parts.append(f"- ms_author: {metadata.ms_author}")
            if metadata.ms_service:
                meta_parts.append(f"- ms_service: {metadata.ms_service}")
            if metadata.customer_intent:
                meta_parts.append(f"- customer_intent: {metadata.customer_intent}")
            if meta_parts:
                parts.append("## User-provided metadata\n" + "\n".join(meta_parts))

        parts.append(
            "## Required output\n"
            "Return ONLY a JSON object matching the DocumentOutline schema shown in your instructions. "
            "Do not include any explanation or prose outside the JSON. "
            "Wrap the JSON in a ```json code fence."
        )

        return "\n\n".join(parts)

    async def _run_agent(self, agent: Agent, user_message: str) -> str:
        """Run the MAF agent and return response text, retrying once on empty response."""
        try:
            result = await agent.run(user_message)
            response_text = result.text or ""
        except Exception:
            logger.exception("structure.agent_run_failed", operation="initial_run")
            raise

        if not response_text.strip():
            logger.warning("structure.empty_response", operation="initial_run")
            try:
                retry_result = await agent.run(
                    user_message + "\n\nIMPORTANT: You must return valid JSON in a ```json code fence."
                )
                response_text = retry_result.text or ""
            except Exception:
                logger.exception("structure.agent_run_failed", operation="retry_run")
                raise

        return response_text

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code fences."""
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1).strip())
        return json.loads(text.strip())

    def _parse_outline(
        self, response_text: str, extraction: ExtractionResult, doc_type: DocType,
        metadata: DocumentMetadata | None = None,
    ) -> DocumentOutline:
        """Parse the LLM JSON response into a DocumentOutline."""
        try:
            data = self._extract_json(response_text)
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.warning(
                "structure.json_parse_failed",
                operation="parse_outline",
                error=str(exc),
            )
            return self._minimal_outline(doc_type, metadata)

        try:
            title = data.get("title", f"{doc_type.value.capitalize()} article")
            description = data.get(
                "description",
                f"Learn how to complete tasks using {doc_type.value} guidance.",
            )
            ms_service = data.get("ms_service", "")
            ms_topic = _MS_TOPIC_MAP.get(doc_type, doc_type.value)

            frontmatter = Frontmatter(
                title=title,
                description=description,
                ms_topic=ms_topic,
                ms_service=ms_service,
                ms_date=datetime.now().strftime("%m/%d/%Y"),
                ai_usage="ai-assisted",
            )

            # Override with user-provided metadata when available
            if metadata:
                if metadata.author:
                    frontmatter.author = metadata.author
                if metadata.ms_author:
                    frontmatter.ms_author = metadata.ms_author
                if metadata.ms_service:
                    frontmatter.ms_service = metadata.ms_service
                if metadata.customer_intent:
                    frontmatter.customer_intent = metadata.customer_intent

            sections: list[DocumentSection] = []
            for raw_section in data.get("sections", []):
                heading = raw_section.get("heading", "")
                if not heading:
                    continue

                tr = raw_section.get("transcript_range") or {}
                transcript_ranges: list[tuple[float, float]] = []
                if tr.get("start") is not None and tr.get("end") is not None:
                    transcript_ranges = [(float(tr["start"]), float(tr["end"]))]

                raw_type = raw_section.get("type", "")
                is_placeholder = raw_type == "placeholder"
                level = int(raw_section.get("level", 2))
                level = max(1, min(level, 4))

                section = DocumentSection(
                    heading=heading,
                    level=level,
                    content_hint=raw_section.get("notes", ""),
                    section_type=raw_type,
                    is_placeholder=is_placeholder,
                    source_scenes=raw_section.get("scene_ids", []),
                    source_transcript_ranges=transcript_ranges,
                )
                sections.append(section)

            outline = DocumentOutline(
                doc_type=doc_type,
                frontmatter=frontmatter,
                sections=sections,
            )

            logger.info(
                "structure.parsed",
                operation="parse_outline",
                title=title,
                sections=len(sections),
            )
            return outline

        except Exception as exc:
            logger.warning(
                "structure.outline_build_failed",
                operation="parse_outline",
                error=str(exc),
            )
            return self._minimal_outline(doc_type, metadata)

    def _minimal_outline(self, doc_type: DocType, metadata: DocumentMetadata | None = None) -> DocumentOutline:
        """Return a minimal fallback outline when LLM response cannot be parsed."""
        logger.warning("structure.using_minimal_fallback", operation="minimal_outline", doc_type=doc_type)
        ms_topic = _MS_TOPIC_MAP.get(doc_type, doc_type.value)
        frontmatter = Frontmatter(
            title=f"{doc_type.value.capitalize()} article",
            description=f"A {doc_type.value} article generated from video content.",
            ms_topic=ms_topic,
            ms_date=datetime.now().strftime("%m/%d/%Y"),
            ai_usage="ai-assisted",
        )
        if metadata:
            if metadata.author:
                frontmatter.author = metadata.author
            if metadata.ms_author:
                frontmatter.ms_author = metadata.ms_author
            if metadata.ms_service:
                frontmatter.ms_service = metadata.ms_service
            if metadata.customer_intent:
                frontmatter.customer_intent = metadata.customer_intent
        return DocumentOutline(
            doc_type=doc_type,
            frontmatter=frontmatter,
            sections=[
                DocumentSection(heading="Introduction", level=2, content_hint="Overview of the topic"),
                DocumentSection(heading="Prerequisites", level=2, content_hint="What you need before starting"),
                DocumentSection(heading="Next steps", level=2, content_hint="Where to go from here"),
            ],
        )

    def _find_best_keyframe(
        self, scene_ids: list[str], extraction: ExtractionResult
    ) -> Keyframe | None:
        """Find the keyframe closest to the midpoint of the referenced scenes."""
        if not scene_ids:
            return None

        scene_map = {s.id: s for s in extraction.scenes}
        keyframe_map = {kf.id: kf for kf in extraction.keyframes}

        candidate_kf_ids: list[str] = []
        midpoints: dict[str, float] = {}

        for scene_id in scene_ids:
            scene = scene_map.get(scene_id)
            if scene:
                midpoint = (scene.start_seconds + scene.end_seconds) / 2.0
                for kf_id in scene.keyframe_ids:
                    candidate_kf_ids.append(kf_id)
                    midpoints[kf_id] = midpoint

        if not candidate_kf_ids:
            return None

        best_id = min(
            candidate_kf_ids,
            key=lambda kf_id: abs(
                (keyframe_map[kf_id].timestamp_seconds if kf_id in keyframe_map else float("inf"))
                - midpoints.get(kf_id, 0.0)
            ),
        )
        return keyframe_map.get(best_id)

    def _attach_screenshots(
        self, outline: DocumentOutline, extraction: ExtractionResult
    ) -> DocumentOutline:
        """Select and attach the best keyframe screenshot for each section."""
        all_screenshots: list[Screenshot] = []
        used_keyframe_ids: set[str] = set()

        for section in outline.sections:
            if not section.source_scenes:
                continue

            keyframe = self._find_best_keyframe(section.source_scenes, extraction)
            if keyframe is None or keyframe.id in used_keyframe_ids:
                continue

            alt_text = keyframe.ui_description or f"Screenshot for section: {section.heading}"
            screenshot = Screenshot(
                keyframe_id=keyframe.id,
                source_path=keyframe.image_path,
                alt_text=alt_text,
            )
            section.screenshots.append(screenshot)
            all_screenshots.append(screenshot)
            used_keyframe_ids.add(keyframe.id)

            logger.debug(
                "structure.screenshot_selected",
                operation="attach_screenshots",
                section=section.heading,
                keyframe_id=keyframe.id,
            )

        outline.screenshots = all_screenshots
        return outline
