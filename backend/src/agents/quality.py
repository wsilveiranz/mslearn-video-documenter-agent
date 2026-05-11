"""Quality Assessment Agent — evaluates extraction data quality for grounding potential."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import structlog
from agent_framework import Agent

from src.models.video import DataQualityReport

if TYPE_CHECKING:
    from agent_framework.foundry import FoundryChatClient

    from src.models.video import ExtractionResult

logger = structlog.get_logger()

_RETRY_MESSAGE = "Please return your quality assessment as valid JSON only, no other text."


class QualityAssessmentAgent:
    """Assesses extraction data quality to determine grounding potential for documentation."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "quality_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a video extraction data quality assessor."
            logger.warning("quality.prompt_not_found", path=str(prompt_path))

    async def process(self, extraction: ExtractionResult) -> DataQualityReport:
        """Assess the quality of extraction data for documentation grounding.

        Args:
            extraction: The extraction result to assess.

        Returns:
            DataQualityReport with quality level, warnings, and recommendations.
        """
        logger.info(
            "quality.start",
            transcript_segments=len(extraction.transcript),
            keyframes=len(extraction.keyframes),
            scenes=len(extraction.scenes),
        )

        raw_metrics = self._compute_raw_metrics(extraction)
        user_message = self._build_user_message(extraction, raw_metrics)

        agent = Agent(
            client=self._client,
            name="QualityAssessmentAgent",
            instructions=self._system_prompt,
        )

        result = await agent.run(user_message)
        response_text: str = result.text

        parsed: dict | None = None
        try:
            parsed = self._extract_json(response_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("quality.parse_failed_retrying", operation="json_parse")
            retry_result = await agent.run(_RETRY_MESSAGE)
            try:
                parsed = self._extract_json(retry_result.text)
            except (json.JSONDecodeError, ValueError):
                logger.error("quality.parse_failed_fallback", operation="json_parse_retry")

        if parsed is None:
            return self._fallback_report(raw_metrics)

        try:
            report = self._build_report(parsed, raw_metrics)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error("quality.build_report_failed", error=str(exc), operation="build_report")
            return self._fallback_report(raw_metrics)

        logger.info(
            "quality.complete",
            quality_level=report.quality_level,
            grounding_confidence=report.grounding_confidence,
            warnings_count=len(report.warnings),
        )
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_raw_metrics(self, extraction: ExtractionResult) -> dict:
        """Compute deterministic metrics from extraction data."""
        transcript_word_count = sum(len(seg.text.split()) for seg in extraction.transcript)
        vision_descriptions = [kf for kf in extraction.keyframes if kf.ui_description]

        # Calculate temporal coverage: how much of the video has transcript
        video_duration = extraction.video_metadata.duration_seconds
        transcript_coverage = 0.0
        if video_duration > 0 and extraction.transcript:
            covered_seconds = sum(
                seg.end_seconds - seg.start_seconds for seg in extraction.transcript
            )
            transcript_coverage = min(covered_seconds / video_duration, 1.0)

        return {
            "transcript_segments": len(extraction.transcript),
            "transcript_word_count": transcript_word_count,
            "transcript_coverage_ratio": round(transcript_coverage, 2),
            "scenes": len(extraction.scenes),
            "keyframes": len(extraction.keyframes),
            "keyframes_with_vision": len(vision_descriptions),
            "ocr_entries": len(extraction.ocr_entries),
            "entities": len(extraction.entities),
            "video_duration_seconds": video_duration,
            "has_audio": extraction.video_metadata.has_audio,
        }

    def _build_user_message(self, extraction: ExtractionResult, raw_metrics: dict) -> str:
        """Build the user message containing extraction data for quality assessment."""
        parts: list[str] = []

        parts.append("## Raw Metrics\n")
        parts.append("```json")
        parts.append(json.dumps(raw_metrics, indent=2))
        parts.append("```\n")

        if extraction.transcript:
            transcript_text = " ".join(seg.text for seg in extraction.transcript)
            # Limit to 4000 chars for assessment context
            parts.append(f"## Transcript ({len(extraction.transcript)} segments)\n")
            parts.append(transcript_text[:4000])
            if len(transcript_text) > 4000:
                parts.append("\n... (truncated)")
            parts.append("")
        else:
            parts.append("## Transcript\n**No transcript available.**\n")

        if extraction.keyframes:
            parts.append(f"## Keyframe Descriptions ({len(extraction.keyframes)} keyframes)\n")
            for kf in extraction.keyframes:
                desc = kf.ui_description or "(no description)"
                parts.append(f"- [{kf.id}] at {kf.timestamp_seconds:.1f}s: {desc}")
            parts.append("")
        else:
            parts.append("## Keyframe Descriptions\n**No keyframes extracted.**\n")

        if extraction.ocr_entries:
            parts.append(f"## OCR Text ({len(extraction.ocr_entries)} entries)\n")
            for entry in extraction.ocr_entries[:30]:
                parts.append(f"- at {entry.timestamp_seconds:.1f}s: {entry.text}")
            if len(extraction.ocr_entries) > 30:
                parts.append(f"... and {len(extraction.ocr_entries) - 30} more")
            parts.append("")
        else:
            parts.append("## OCR Text\n**No OCR text detected.**\n")

        if extraction.scenes:
            parts.append(f"## Scenes ({len(extraction.scenes)} detected)\n")
            for scene in extraction.scenes:
                parts.append(
                    f"- [{scene.id}] {scene.start_seconds:.1f}s-{scene.end_seconds:.1f}s: "
                    f"{scene.description or '(no description)'}"
                )
            parts.append("")

        parts.append(
            "\n## Instructions\n\n"
            "Assess the quality and grounding potential of this extraction data. "
            "Return your assessment as a JSON object only."
        )

        return "\n".join(parts)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code fences."""
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(text)

    def _build_report(self, parsed: dict, raw_metrics: dict) -> DataQualityReport:
        """Map parsed LLM JSON to DataQualityReport."""
        quality_level = parsed.get("quality_level", "thin")
        if quality_level not in ("rich", "adequate", "thin", "minimal"):
            quality_level = "thin"

        grounding_confidence = float(parsed.get("grounding_confidence", 0.3))
        grounding_confidence = max(0.0, min(1.0, grounding_confidence))

        return DataQualityReport(
            quality_level=quality_level,
            transcript_assessment=parsed.get("transcript_assessment", "Assessment unavailable."),
            visual_assessment=parsed.get("visual_assessment", "Assessment unavailable."),
            coverage_gaps=parsed.get("coverage_gaps", []),
            warnings=parsed.get("warnings", []),
            recommendations=parsed.get("recommendations", []),
            grounding_confidence=grounding_confidence,
            raw_metrics=raw_metrics,
        )

    def _fallback_report(self, raw_metrics: dict) -> DataQualityReport:
        """Return a conservative fallback report when LLM parsing fails."""
        # Heuristic: if we have some transcript and some vision, call it "thin" not "minimal"
        has_transcript = raw_metrics.get("transcript_segments", 0) > 0
        has_vision = raw_metrics.get("keyframes_with_vision", 0) > 0

        if has_transcript and has_vision:
            level: Literal["rich", "adequate", "thin", "minimal"] = "thin"
            confidence = 0.4
        elif has_transcript or has_vision:
            level = "thin"
            confidence = 0.3
        else:
            level = "minimal"
            confidence = 0.1

        return DataQualityReport(
            quality_level=level,
            transcript_assessment="Quality assessment could not be completed — LLM response parsing failed.",
            visual_assessment="Quality assessment could not be completed — LLM response parsing failed.",
            coverage_gaps=["Unable to determine coverage gaps due to assessment failure."],
            warnings=["Quality assessment failed — manual review recommended before generating documentation."],
            recommendations=["Re-run quality assessment or provide supplementary context."],
            grounding_confidence=confidence,
            raw_metrics=raw_metrics,
        )
