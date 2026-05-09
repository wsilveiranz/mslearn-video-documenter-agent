"""Reference-based evaluation — compare generated docs against a published MS Learn article.

Uses the published article as a rubric to score how well the pipeline output
matches the real documentation in topic, structure, steps, and terminology.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
from agent_framework import Agent

pytestmark = [pytest.mark.eval, pytest.mark.integration]

_REFERENCE_CACHE_FILENAME = "reference_article.md"

_JUDGE_SYSTEM_PROMPT = """\
You are an expert documentation evaluator. You compare a generated document \
against a published reference article to assess how well the generated version \
captures the same content.

Score each dimension from 0.0 to 1.0. Return ONLY a JSON object — no prose.

```json
{
  "topic_alignment": 0.0,
  "section_coverage": 0.0,
  "step_completeness": 0.0,
  "terminology_accuracy": 0.0,
  "summary": ""
}
```

## Scoring dimensions

### topic_alignment (0.0-1.0)
Does the generated document cover the same subject as the reference?
- 1.0: Exact same topic, product, and scenario.
- 0.7: Same product area but slightly different focus.
- 0.4: Tangentially related Azure topic.
- 0.0: Completely unrelated topic.

### section_coverage (0.0-1.0)
Are the major sections and headings from the reference represented?
List the reference H2/H3 headings and check how many have a counterpart \
(exact or semantic match) in the generated document.
- 1.0: All major sections represented.
- 0.7: Most sections present, one or two minor ones missing.
- 0.4: Only about half the sections are covered.
- 0.0: Almost no section overlap.

### step_completeness (0.0-1.0)
Are the key procedural steps from the reference covered?
Compare numbered steps in procedural sections. A step counts as covered if \
the same action is described, even with different wording.
- 1.0: All procedural steps covered.
- 0.7: Most steps present, minor ones missing.
- 0.4: Key steps present but significant gaps.
- 0.0: Steps are mostly missing or wrong.

### terminology_accuracy (0.0-1.0)
Does the generated document use the correct product names, UI elements, \
menu paths, and technical terms from the reference?
- 1.0: All key terms match (e.g., "Clone to Standard", "Consumption logic app").
- 0.7: Most terms correct, minor naming differences.
- 0.4: Some incorrect product names or UI element labels.
- 0.0: Pervasive terminology errors.

### summary
A 2-3 sentence summary explaining the scores. Highlight the biggest gap \
between the generated document and the reference.
"""


def _fetch_reference_article(url: str, cache_dir: Path) -> str:
    """Fetch the reference article from MS Learn, caching locally."""
    cache_path = cache_dir / _REFERENCE_CACHE_FILENAME
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    # Fetch as plain text (MS Learn renders HTML; we request the page and extract text)
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()

    # Strip HTML to plain text — keep structure visible
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            self._skip = tag in ("script", "style", "nav", "footer", "header")
            if tag in ("h1", "h2", "h3", "h4"):
                level = int(tag[1])
                self._parts.append("\n" + "#" * level + " ")
            elif tag == "li":
                self._parts.append("\n- ")
            elif tag == "p":
                self._parts.append("\n\n")
            elif tag == "br":
                self._parts.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav", "footer", "header"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                self._parts.append(data)

    extractor = _TextExtractor()
    extractor.feed(response.text)
    text = "".join(extractor._parts).strip()

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    cache_path.write_text(text, encoding="utf-8")
    return text


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    return json.loads(text.strip())


@pytest.mark.asyncio
async def test_reference_comparison(eval_output, reference_url, foundry_client):
    """Compare pipeline output against the published MS Learn article."""

    # Load the generated document
    doc_path = eval_output / "pipeline_document.md"
    if not doc_path.exists():
        pytest.skip(
            "No pipeline_document.md -- run pipeline eval first "
            "(pytest -m eval tests/eval/test_eval_pipeline.py)"
        )

    generated_doc = doc_path.read_text(encoding="utf-8")

    # Fetch and cache reference article
    reference_text = _fetch_reference_article(reference_url, eval_output)
    assert len(reference_text) > 500, (
        f"Reference article too short ({len(reference_text)} chars) -- fetch may have failed"
    )

    # Build the comparison prompt
    user_message = (
        "## Reference article (published on Microsoft Learn)\n\n"
        f"{reference_text[:8000]}\n\n"
        "---\n\n"
        "## Generated document (from video processing pipeline)\n\n"
        f"{generated_doc[:8000]}\n\n"
        "---\n\n"
        "Compare the generated document against the reference article. "
        "Score each dimension and return your assessment as JSON."
    )

    agent = Agent(
        client=foundry_client,
        name="ReferenceEvaluator",
        instructions=_JUDGE_SYSTEM_PROMPT,
    )
    result = await agent.run(user_message)
    response_text: str = result.text

    # Parse scores
    try:
        scores = _extract_json(response_text)
    except (json.JSONDecodeError, ValueError):
        # Retry once
        retry_result = await agent.run(
            "Please return your evaluation as valid JSON only, no other text."
        )
        scores = _extract_json(retry_result.text)

    # Save results
    scores_path = eval_output / "reference_eval.json"
    scores_path.write_text(json.dumps(scores, indent=2), encoding="utf-8")

    # Display results
    topic = scores.get("topic_alignment", 0)
    sections = scores.get("section_coverage", 0)
    steps = scores.get("step_completeness", 0)
    terminology = scores.get("terminology_accuracy", 0)
    overall = (topic + sections + steps + terminology) / 4
    summary = scores.get("summary", "")

    print(f"\n{'='*60}")
    print("REFERENCE-BASED EVALUATION")
    print(f"{'='*60}")
    print(f"Reference URL:         {reference_url}")
    print(f"Topic alignment:       {topic:.2f}")
    print(f"Section coverage:      {sections:.2f}")
    print(f"Step completeness:     {steps:.2f}")
    print(f"Terminology accuracy:  {terminology:.2f}")
    print(f"Overall:               {overall:.2f}")
    print(f"\nSummary: {summary}")
    print(f"\nArtifacts saved to: {scores_path}")

    # Assertions — the generated doc should at least be on-topic
    assert topic >= 0.5, (
        f"Topic alignment too low ({topic:.2f}) — "
        "generated document doesn't match the reference article's subject"
    )
    assert overall >= 0.3, (
        f"Overall reference score too low ({overall:.2f}) — "
        "generated document diverges significantly from the reference"
    )
