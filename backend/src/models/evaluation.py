"""Data models for document quality evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationScores(BaseModel):
    """Individual evaluation dimension scores."""

    completeness: float = Field(ge=0.0, le=1.0, description="Are all video steps represented?")
    accuracy: float = Field(ge=0.0, le=1.0, description="Does text match what's shown in video?")
    style_compliance: float = Field(ge=0.0, le=1.0, description="Does it follow MS Learn voice/tone?")
    readability: float = Field(ge=0.0, le=1.0, description="Is it scannable, concise, well-structured?")
    grounding: float = Field(default=0.5, ge=0.0, le=1.0, description="Is content traceable to extraction evidence?")

    @property
    def overall(self) -> float:
        """Average of all dimension scores."""
        scores = [self.completeness, self.accuracy, self.style_compliance, self.readability, self.grounding]
        return sum(scores) / len(scores)

    @property
    def passed(self) -> bool:
        """True if overall >= 0.7 and no dimension below 0.5."""
        all_scores = [
            self.completeness, self.accuracy, self.style_compliance,
            self.readability, self.grounding,
        ]
        return self.overall >= 0.7 and all(s >= 0.5 for s in all_scores)


class EvaluationSuggestion(BaseModel):
    """A specific improvement suggestion from the evaluator."""

    dimension: str = Field(description="Which dimension this suggestion addresses")
    section: str = Field(default="", description="Target section heading, if applicable")
    issue: str = Field(description="What the problem is")
    suggestion: str = Field(description="How to fix it")
    severity: str = Field(default="medium", description="low, medium, high")


class EvaluationReport(BaseModel):
    """Complete evaluation report from the Evaluate Agent."""

    document_id: str
    scores: EvaluationScores
    passed: bool = Field(description="Whether the document meets quality threshold")
    suggestions: list[EvaluationSuggestion] = Field(default_factory=list)
    summary: str = Field(default="", description="Human-readable evaluation summary")
    iteration: int = Field(default=1, description="Which revision iteration this evaluates")
