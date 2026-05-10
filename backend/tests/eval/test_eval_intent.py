"""Evaluate intent classification with real LLM calls.

Tests the classification prompt against a curated dataset of user messages
to ensure the LLM correctly distinguishes save, refine, and general intents.

Run with: pytest tests/eval/test_eval_intent.py -m eval -v
"""

from __future__ import annotations

import pytest

from src.services.intent_classifier import (
    ClassificationResult,
    classify_intent,
    classify_intent_fast,
    parse_llm_response,
)

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


# ---- Test dataset: (prompt, expected_intent) ----

SAVE_PROMPTS = [
    "save to c:\\temp\\",
    "save the file to /home/user/docs",
    "export to D:\\output",
    "please save to c:\\temp\\",
    "copy it to c:\\docs",
    "write it to /tmp/output.md",
    "save",
    "export",
    "save the document",
    # Ambiguous save (needs LLM)
    "put the file on my desktop",
    "can you write this to disk",
    "I want this in my downloads folder",
    "store it somewhere on my machine",
    "output the markdown to a file",
]

REFINE_PROMPTS = [
    "make the introduction more concise",
    "add a note about prerequisites",
    "the step 3 description is wrong, fix it",
    "rewrite the conclusion",
    "change the title to something shorter",
    "remove the section about cleanup",
    "add more detail to the code examples",
    "fix the formatting in the prerequisites section",
    "make it sound more professional",
    "can you add screenshots descriptions",
    "the tone is too casual, make it more formal",
    "merge steps 2 and 3",
]

GENERAL_PROMPTS = [
    "what commands are available?",
    "how does this tool work?",
    "what types of documents can you generate?",
    "help",
    "what is MS Learn?",
    "can you explain the difference between a tutorial and a quickstart?",
    "what video formats do you support?",
    "who made this extension?",
]


@pytest.mark.asyncio
async def test_llm_classifies_save_intents(foundry_client):
    """LLM should classify save-related prompts correctly."""
    results: list[tuple[str, ClassificationResult]] = []

    for prompt in SAVE_PROMPTS:
        result = await classify_intent(prompt, foundry_client)
        results.append((prompt, result))

    print(f"\n{'='*60}")
    print("SAVE INTENT CLASSIFICATION")
    print(f"{'='*60}")

    correct = 0
    for prompt, result in results:
        status = "PASS" if result.intent == "save" else "FAIL"
        if result.intent == "save":
            correct += 1
        print(f"  {status} [{result.confidence}] \"{prompt}\" -> {result.intent}")

    accuracy = correct / len(SAVE_PROMPTS) * 100
    print(f"\nAccuracy: {correct}/{len(SAVE_PROMPTS)} ({accuracy:.0f}%)")

    # Allow some tolerance for ambiguous prompts, but core ones must pass
    assert accuracy >= 80, f"Save intent accuracy too low: {accuracy:.0f}%"


@pytest.mark.asyncio
async def test_llm_classifies_refine_intents(foundry_client):
    """LLM should classify refinement prompts correctly."""
    results: list[tuple[str, ClassificationResult]] = []

    for prompt in REFINE_PROMPTS:
        result = await classify_intent(prompt, foundry_client)
        results.append((prompt, result))

    print(f"\n{'='*60}")
    print("REFINE INTENT CLASSIFICATION")
    print(f"{'='*60}")

    correct = 0
    for prompt, result in results:
        status = "PASS" if result.intent == "refine" else "FAIL"
        if result.intent == "refine":
            correct += 1
        print(f"  {status} [{result.confidence}] \"{prompt}\" -> {result.intent}")

    accuracy = correct / len(REFINE_PROMPTS) * 100
    print(f"\nAccuracy: {correct}/{len(REFINE_PROMPTS)} ({accuracy:.0f}%)")

    # Refinement is the most critical — the original bug was misclassified save
    assert accuracy >= 90, f"Refine intent accuracy too low: {accuracy:.0f}%"


@pytest.mark.asyncio
async def test_llm_classifies_general_intents(foundry_client):
    """LLM should classify general conversation prompts correctly."""
    results: list[tuple[str, ClassificationResult]] = []

    for prompt in GENERAL_PROMPTS:
        result = await classify_intent(prompt, foundry_client)
        results.append((prompt, result))

    print(f"\n{'='*60}")
    print("GENERAL INTENT CLASSIFICATION")
    print(f"{'='*60}")

    correct = 0
    for prompt, result in results:
        status = "PASS" if result.intent == "general" else "FAIL"
        if result.intent == "general":
            correct += 1
        print(f"  {status} [{result.confidence}] \"{prompt}\" -> {result.intent}")

    accuracy = correct / len(GENERAL_PROMPTS) * 100
    print(f"\nAccuracy: {correct}/{len(GENERAL_PROMPTS)} ({accuracy:.0f}%)")

    assert accuracy >= 75, f"General intent accuracy too low: {accuracy:.0f}%"


@pytest.mark.asyncio
async def test_save_vs_refine_confusion(foundry_client):
    """The most critical test: save must NEVER be classified as refine."""
    critical_save = [
        "save to c:\\temp\\",
        "save the file to /home/user/docs",
        "export to D:\\output",
        "I want this in my downloads folder",
        "put it in c:\\users\\me\\desktop\\",
    ]

    misclassified = []
    for prompt in critical_save:
        result = await classify_intent(prompt, foundry_client)
        if result.intent == "refine":
            misclassified.append((prompt, result))

    if misclassified:
        print("\n⚠️ CRITICAL: Save prompts misclassified as refine:")
        for prompt, result in misclassified:
            print(f"  \"{prompt}\" -> {result.intent} (raw: {result.raw_response})")

    assert len(misclassified) == 0, (
        f"{len(misclassified)} save prompts misclassified as refine — "
        "this is the exact bug from #30"
    )
