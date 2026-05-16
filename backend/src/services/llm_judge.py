"""LLM-as-judge evaluation service for MS Learn documentation quality."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from src.utils.paths import get_prompts_dir

if TYPE_CHECKING:
    from agent_framework.foundry import FoundryChatClient

logger = structlog.get_logger()

DIMENSIONS = ("voice_tone", "grounding", "accuracy", "completeness")

_FALLBACK_REASONING = "Parse failed — score set to neutral 0.5. Manual review required."


@dataclass
class JudgeResult:
    """Result of an LLM-as-judge evaluation for a single dimension."""

    dimension: str
    score: float  # 0.0 to 1.0
    reasoning: str
    sub_scores: dict[str, float] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)


class LLMJudge:
    """LLM-as-judge service that evaluates MS Learn documentation on four quality dimensions."""

    def __init__(self, client: FoundryChatClient) -> None:
        self._client = client
        self._rubrics: dict[str, str] = {}

    def _load_rubric(self, dimension: str) -> str:
        """Load rubric prompt for the given dimension, with caching."""
        if dimension in self._rubrics:
            return self._rubrics[dimension]

        prompt_path = get_prompts_dir() / f"judge_{dimension}.md"
        try:
            text = prompt_path.read_text(encoding="utf-8")
            self._rubrics[dimension] = text
            return text
        except FileNotFoundError:
            logger.warning("llm_judge.rubric_not_found", dimension=dimension, path=str(prompt_path))
            fallback = f"You are a Microsoft Learn documentation quality evaluator for the {dimension} dimension."
            self._rubrics[dimension] = fallback
            return fallback

    def _build_user_message(self, document_text: str, context: dict | None) -> str:
        parts = [
            "## Document to evaluate\n",
            f"```markdown\n{document_text}\n```",
        ]
        if context:
            parts.append("\n## Additional context\n")
            for key, value in context.items():
                if isinstance(value, list):
                    formatted = "\n".join(f"- {item}" for item in value)
                    parts.append(f"### {key}\n{formatted}")
                else:
                    parts.append(f"### {key}\n{value}")
        parts.append("\nEvaluate the document and return your assessment as JSON only.")
        return "\n\n".join(parts)

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response, handling markdown code fences."""
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return json.loads(text)

    def _fallback_result(self, dimension: str) -> JudgeResult:
        return JudgeResult(
            dimension=dimension,
            score=0.5,
            reasoning=_FALLBACK_REASONING,
            sub_scores={},
            evidence=[],
        )

    async def evaluate(
        self,
        document_text: str,
        dimension: str,
        context: dict | None = None,
    ) -> JudgeResult:
        """Evaluate a document on a single quality dimension.

        Args:
            document_text: The Markdown document content to evaluate.
            dimension: One of "voice_tone", "grounding", "accuracy", "completeness".
            context: Optional dict with additional context (e.g., transcript for grounding).

        Returns:
            JudgeResult with score (0.0–1.0), reasoning, sub_scores, and evidence.
        """
        logger.info("llm_judge.evaluate", dimension=dimension, doc_length=len(document_text))

        system_prompt = self._load_rubric(dimension)
        user_message = self._build_user_message(document_text, context)

        from agent_framework import Agent

        agent = Agent(
            client=self._client,
            name=f"LLMJudge_{dimension}",
            instructions=system_prompt,
        )

        response_text: str = ""
        try:
            result = await agent.run(user_message)
            response_text = result.text
            parsed = self._extract_json(response_text)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "llm_judge.parse_failed_retrying",
                dimension=dimension,
                error=str(e),
            )
            try:
                retry_result = await agent.run(
                    "Please return your evaluation as valid JSON only, no other text."
                )
                response_text = retry_result.text
                parsed = self._extract_json(response_text)
            except (json.JSONDecodeError, ValueError) as retry_e:
                logger.error("llm_judge.parse_failed", dimension=dimension, error=str(retry_e))
                return self._fallback_result(dimension)
        except Exception as e:
            logger.error("llm_judge.request_failed", dimension=dimension, error=str(e))
            return self._fallback_result(dimension)

        try:
            judge_result = JudgeResult(
                dimension=dimension,
                score=float(parsed["score"]),
                reasoning=parsed.get("reasoning", ""),
                sub_scores={k: float(v) for k, v in parsed.get("sub_scores", {}).items()},
                evidence=list(parsed.get("evidence", [])),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error("llm_judge.build_result_failed", dimension=dimension, error=str(e))
            return self._fallback_result(dimension)

        logger.info("llm_judge.result", dimension=dimension, score=judge_result.score)
        return judge_result

    async def evaluate_all(
        self,
        document_text: str,
        context: dict | None = None,
    ) -> dict[str, JudgeResult]:
        """Evaluate a document on all four quality dimensions.

        Args:
            document_text: The Markdown document content to evaluate.
            context: Optional dict passed to each dimension's evaluator.

        Returns:
            Dict mapping dimension name to JudgeResult.
        """
        import asyncio

        tasks = {
            dim: self.evaluate(document_text, dim, context)
            for dim in DIMENSIONS
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        output: dict[str, JudgeResult] = {}
        for dim, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error("llm_judge.dimension_failed", dimension=dim, error=str(result))
                output[dim] = self._fallback_result(dim)
            else:
                output[dim] = result  # type: ignore[assignment]

        return output
