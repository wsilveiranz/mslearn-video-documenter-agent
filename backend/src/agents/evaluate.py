"""Evaluate Agent — quality-gates documents with scoring and suggestions."""

from __future__ import annotations

from pathlib import Path

import structlog

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from src.models.document import GeneratedDocument
from src.models.evaluation import EvaluationReport, EvaluationScores, EvaluationSuggestion
from src.models.video import ExtractionResult

logger = structlog.get_logger()


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

        # TODO Phase 1: Use MAF Agent to evaluate
        # - Send document + extraction summary + rubric
        # - Parse structured scores from LLM response
        # - Generate suggestions

        agent = Agent(
            client=self._client,
            name="EvaluateAgent",
            instructions=self._system_prompt,
        )

        # Placeholder scores
        scores = EvaluationScores(
            completeness=0.0,
            accuracy=0.0,
            style_compliance=0.0,
            readability=0.0,
        )

        report = EvaluationReport(
            document_id=document.document_id,
            scores=scores,
            passed=scores.passed,
            suggestions=[],
            summary="Evaluation not yet implemented — placeholder scores.",
        )

        logger.info(
            "evaluate.complete",
            doc_id=document.document_id,
            overall=scores.overall,
            passed=report.passed,
        )
        return report
