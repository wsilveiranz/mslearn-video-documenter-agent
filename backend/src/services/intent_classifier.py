"""Intent classification service for routing user messages.

Classifies free-form user messages into actionable intents so that
the chat handler can route them to the correct operation (save, refine,
or general conversation) instead of blindly treating everything as
refinement feedback.
"""

from __future__ import annotations

import re
from typing import Literal

import structlog
from agent_framework.foundry import FoundryChatClient
from pydantic import BaseModel, Field

logger = structlog.get_logger()

IntentLabel = Literal["save", "refine", "general"]


class ClassificationResult(BaseModel):
    """Result of intent classification."""

    intent: IntentLabel
    confidence: str = Field(
        description="How the intent was determined: 'pattern' (regex) or 'llm' (model)"
    )
    raw_response: str | None = Field(
        default=None, description="Raw LLM response text (only for llm confidence)"
    )


# Fast-path regex patterns for save/export intent
SAVE_PATTERNS: list[re.Pattern[str]] = [
    # "save/export to <path-like>" — require a filesystem-looking destination
    re.compile(
        r"^(please\s+)?(save|export|write|copy)\s+"
        r"(it\s+|the\s+(doc|document|file|markdown|md)\s+)?"
        r"(to|at|into)\s+[\"']?([a-zA-Z]:[/\\]|[/~.])",
        re.IGNORECASE,
    ),
    # "save/export it" or "save the document" (bare, no destination)
    re.compile(
        r"^(please\s+)?(save|export)\s+"
        r"(it|this|the\s+(doc|document|file|markdown|md))?\s*$",
        re.IGNORECASE,
    ),
    # bare "save" or "export"
    re.compile(r"^(please\s+)?(save|export)\s*$", re.IGNORECASE),
]

CLASSIFICATION_PROMPT = (
    "Classify the following user message into exactly one category. "
    "The user has a generated document open.\n\n"
    "Categories:\n"
    '- "save": The user wants to save, export, download, or copy the document '
    "to a file or location\n"
    '- "refine": The user is providing feedback to improve, edit, or change '
    "the document content\n"
    '- "general": The user is asking a question, requesting help, or making a '
    "request unrelated to modifying the document\n\n"
    "Respond with ONLY the category name (save, refine, or general). "
    "No explanation.\n\n"
    'User message: "{message}"'
)


def classify_intent_fast(prompt: str) -> ClassificationResult | None:
    """Classify intent using fast regex pattern matching.

    Returns a ClassificationResult if a save pattern matches,
    None if the prompt needs LLM classification.
    """
    trimmed = prompt.strip()
    for pattern in SAVE_PATTERNS:
        if pattern.search(trimmed):
            return ClassificationResult(intent="save", confidence="pattern")
    return None


def parse_llm_response(raw: str) -> IntentLabel:
    """Parse the raw LLM classification response into an IntentLabel.

    Handles variations like "save", "Save", "save.", "The intent is save", etc.
    Defaults to 'refine' for unrecognised responses (preserves legacy behaviour).
    """
    cleaned = raw.strip().lower()

    # Direct match
    if cleaned in ("save", "refine", "general"):
        return cleaned  # type: ignore[return-value]

    # Substring match (handles "save." or "The category is save")
    if "save" in cleaned:
        return "save"
    if "general" in cleaned:
        return "general"
    if "refine" in cleaned:
        return "refine"

    # Default: treat as refinement (preserves original behaviour)
    logger.warn(
        "llm_classification_unrecognised",
        raw_response=raw,
        fallback="refine",
    )
    return "refine"


async def classify_intent(
    prompt: str,
    client: FoundryChatClient,
) -> ClassificationResult:
    """Classify a user message intent, using regex fast path then LLM fallback.

    Args:
        prompt: The user's free-form message.
        client: FoundryChatClient for LLM classification.

    Returns:
        ClassificationResult with the determined intent.
    """
    # Fast path
    fast = classify_intent_fast(prompt)
    if fast is not None:
        logger.debug("intent_classified", intent=fast.intent, confidence="pattern", prompt=prompt[:80])
        return fast

    # LLM fallback
    formatted = CLASSIFICATION_PROMPT.format(message=prompt.strip())

    try:
        response = await client.complete(
            messages=[{"role": "user", "content": formatted}]
        )
        raw = response.choices[0].message.content.strip()
        intent = parse_llm_response(raw)

        logger.info(
            "intent_classified",
            intent=intent,
            confidence="llm",
            prompt=prompt[:80],
            raw_response=raw,
        )
        return ClassificationResult(intent=intent, confidence="llm", raw_response=raw)

    except Exception as e:
        logger.error(
            "intent_classification_failed",
            error=str(e),
            prompt=prompt[:80],
            fallback="refine",
        )
        return ClassificationResult(intent="refine", confidence="llm", raw_response=None)
