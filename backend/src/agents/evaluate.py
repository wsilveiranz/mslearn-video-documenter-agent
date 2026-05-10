"""Evaluate Agent — quality-gates documents with scoring and suggestions."""

from __future__ import annotations

import json
import re
from pathlib import Path

import structlog
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from src.models.document import GeneratedDocument
from src.models.evaluation import EvaluationReport, EvaluationScores, EvaluationSuggestion
from src.models.video import ExtractionResult

logger = structlog.get_logger()

_RETRY_MESSAGE = "Please return your evaluation as valid JSON only, no other text."

_FALLBACK_SUMMARY = (
    "Evaluation parsing failed — conservative mid-range scores assigned. "
    "Manual review required."
)


class EvaluateAgent:
    """Evaluates documents on completeness, accuracy, style, and readability."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._load_system_prompt()

    def _load_system_prompt(self) -> None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "evaluate_system.md"
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._system_prompt = "You are a Microsoft Learn documentation quality evaluator."
            logger.warning("evaluate.prompt_not_found", path=str(prompt_path))

    async def process(
        self, document: GeneratedDocument, extraction: ExtractionResult
    ) -> EvaluationReport:
        """Evaluate a generated document against quality criteria.

        Args:
            document: The document to evaluate.
            extraction: Original extraction data for accuracy comparison.

        Returns:
            EvaluationReport with scores and suggestions.
        """
        logger.info("evaluate.start", doc_id=document.document_id)

        user_message = self._build_user_message(document, extraction)

        agent = Agent(
            client=self._client,
            name="EvaluateAgent",
            instructions=self._system_prompt,
        )
        result = await agent.run(user_message)
        response_text: str = result.text

        parsed: dict | None = None
        try:
            parsed = self._extract_json(response_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "evaluate.parse_failed_retrying",
                doc_id=document.document_id,
                operation="json_parse",
            )
            retry_result = await agent.run(_RETRY_MESSAGE)
            retry_text: str = retry_result.text
            try:
                parsed = self._extract_json(retry_text)
            except (json.JSONDecodeError, ValueError):
                logger.error(
                    "evaluate.parse_failed_fallback",
                    doc_id=document.document_id,
                    operation="json_parse_retry",
                )

        if parsed is None:
            return self._fallback_report(document.document_id)

        try:
            report = self._build_report(document.document_id, parsed)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error(
                "evaluate.build_report_failed",
                doc_id=document.document_id,
                operation="build_report",
                error=str(exc),
            )
            return self._fallback_report(document.document_id)

        logger.info(
            "evaluate.complete",
            doc_id=document.document_id,
            overall=report.scores.overall,
            passed=report.passed,
        )
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_user_message(
        self, document: GeneratedDocument, extraction: ExtractionResult
    ) -> str:
        extraction_summary = self._build_extraction_summary(extraction)
        return (
            f"## Document to evaluate\n\n"
            f"Document ID: {document.document_id}\n"
            f"Document type: {document.doc_type.value}\n\n"
            f"```markdown\n{document.markdown_content}\n```\n\n"
            f"## Extraction data (for accuracy and completeness verification)\n\n"
            f"{extraction_summary}\n\n"
            "Evaluate this document and return your assessment as JSON."
        )

    def _build_extraction_summary(self, extraction: ExtractionResult) -> str:
        """Build a concise extraction summary for evaluation context."""
        parts: list[str] = []
        if extraction.transcript:
            transcript = " ".join(seg.text for seg in extraction.transcript)
            parts.append(
                f"Transcript ({len(extraction.transcript)} segments):\n{transcript[:3000]}"
            )
        parts.append(f"Scenes: {len(extraction.scenes)}")
        parts.append(f"Keyframes: {len(extraction.keyframes)}")
        if extraction.ocr_entries:
            ocr = ", ".join(e.text for e in extraction.ocr_entries[:20])
            parts.append(f"OCR text: {ocr}")
        return "\n".join(parts)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code fences."""
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(text)

    def _build_report(self, document_id: str, parsed: dict) -> EvaluationReport:
        """Map parsed LLM JSON to EvaluationReport, handling field name variants."""
        raw_scores: dict = parsed["scores"]

        # The system prompt returns "technical_accuracy"; EvaluationScores uses "accuracy".
        accuracy = raw_scores.get("accuracy") or raw_scores.get("technical_accuracy", 0.5)

        scores = EvaluationScores(
            completeness=raw_scores["completeness"],
            accuracy=accuracy,
            style_compliance=raw_scores["style_compliance"],
            readability=raw_scores["readability"],
        )

        suggestions: list[EvaluationSuggestion] = []
        for item in parsed.get("suggestions", []):
            # Map prompt's major/minor severity to model's low/medium/high.
            raw_severity: str = item.get("severity", "medium")
            severity = _normalise_severity(raw_severity)
            suggestions.append(
                EvaluationSuggestion(
                    dimension=item["dimension"],
                    section=item.get("section", ""),
                    issue=item["issue"],
                    suggestion=item["suggestion"],
                    severity=severity,
                )
            )

        return EvaluationReport(
            document_id=document_id,
            scores=scores,
            passed=scores.passed,
            suggestions=suggestions,
            summary=parsed.get("summary", ""),
        )

    def _fallback_report(self, document_id: str) -> EvaluationReport:
        """Return a conservative mid-range report when parsing fails."""
        scores = EvaluationScores(
            completeness=0.5,
            accuracy=0.5,
            style_compliance=0.5,
            readability=0.5,
        )
        return EvaluationReport(
            document_id=document_id,
            scores=scores,
            passed=False,
            suggestions=[],
            summary=_FALLBACK_SUMMARY,
        )


def _normalise_severity(raw: str) -> str:
    """Map major/minor (prompt convention) to high/low (model convention)."""
    mapping = {"major": "high", "minor": "low"}
    return mapping.get(raw.lower(), raw.lower() if raw.lower() in {"low", "medium", "high"} else "medium")
