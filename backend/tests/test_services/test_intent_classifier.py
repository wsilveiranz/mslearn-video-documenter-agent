"""Unit tests for the intent classifier — no LLM calls needed."""

from __future__ import annotations

import pytest

from src.services.intent_classifier import classify_intent_fast, parse_llm_response

pytestmark = pytest.mark.unit


# ---- classify_intent_fast ----


class TestClassifyIntentFast:
    """Tests for regex-based fast path classification."""

    @pytest.mark.parametrize(
        "prompt",
        [
            "save to c:\\temp\\",
            "save it to /home/user/docs",
            "export to D:\\output",
            "save the document to ./output",
            "please save to c:\\temp\\",
            "copy it to c:\\docs",
            "write the doc to /tmp/",
            "save",
            "export",
            "Save It",
            "EXPORT TO C:\\TEMP\\",
            "save the markdown",
            "export the file",
        ],
    )
    def test_detects_save_intent(self, prompt: str):
        result = classify_intent_fast(prompt)
        assert result is not None, f"Expected save for: {prompt!r}"
        assert result.intent == "save"
        assert result.confidence == "pattern"

    @pytest.mark.parametrize(
        "prompt",
        [
            "make the introduction more concise",
            "add a note about prerequisites",
            "what commands are available?",
            "can you fix the formatting?",
            "",
            "   ",
            "I want to learn about tutorials",
            "put the file on my desktop",  # ambiguous — should go to LLM
            # Regression: refinement phrased with save/write verbs (issue #30 review)
            "write it in a more formal tone",
            "write the document in a different style",
            "save the doc in a shorter format",
            "copy it in a table format",
            "write it in markdown format",
            "save it as a bullet list",
        ],
    )
    def test_returns_none_for_non_save(self, prompt: str):
        result = classify_intent_fast(prompt)
        assert result is None, f"Expected None (LLM fallback) for: {prompt!r}"


# ---- parse_llm_response ----


class TestParseLlmResponse:
    """Tests for parsing raw LLM classification output."""

    def test_exact_save(self):
        assert parse_llm_response("save") == "save"

    def test_exact_refine(self):
        assert parse_llm_response("refine") == "refine"

    def test_exact_general(self):
        assert parse_llm_response("general") == "general"

    def test_case_insensitive(self):
        assert parse_llm_response("Save") == "save"
        assert parse_llm_response("REFINE") == "refine"
        assert parse_llm_response("General") == "general"

    def test_with_trailing_period(self):
        assert parse_llm_response("save.") == "save"
        assert parse_llm_response("refine.") == "refine"

    def test_with_whitespace(self):
        assert parse_llm_response("  save  ") == "save"
        assert parse_llm_response("\nrefine\n") == "refine"

    def test_verbose_response_save(self):
        assert parse_llm_response("The category is save") == "save"

    def test_verbose_response_refine(self):
        assert parse_llm_response("I would classify this as refine") == "refine"

    def test_verbose_response_general(self):
        assert parse_llm_response("This is a general question") == "general"

    def test_quoted_response(self):
        assert parse_llm_response('"save"') == "save"
        assert parse_llm_response("'refine'") == "refine"

    def test_unrecognised_defaults_to_refine(self):
        assert parse_llm_response("I don't know") == "refine"

    def test_empty_defaults_to_refine(self):
        assert parse_llm_response("") == "refine"

    def test_priority_save_over_refine(self):
        """If response somehow mentions both, save takes priority."""
        assert parse_llm_response("save not refine") == "save"

    def test_priority_general_over_refine(self):
        """General before refine in check order."""
        assert parse_llm_response("this is general not refine") == "general"
