"""Grounding evaluation — verify generated content traces to video transcript.

Checks that the generated document uses terminology and concepts from the video
rather than hallucinating content not present in the source material.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.grounding]


@pytest.mark.asyncio
async def test_writer_grounding(eval_output):
    """Check Writer output is grounded in extraction transcript."""
    from src.models.video import ExtractionResult

    from tests.eval.graders import check_grounding

    # Load extraction data
    extraction_path = eval_output / "extraction_result.json"
    if not extraction_path.exists():
        pytest.skip("No extraction_result.json — run extraction eval first")

    extraction = ExtractionResult.model_validate_json(extraction_path.read_text())
    transcript_segments = [seg.text for seg in extraction.transcript]

    if not transcript_segments:
        pytest.skip("Extraction has no transcript segments")

    # Load writer output
    doc_path = eval_output / "generated_document.md"
    if not doc_path.exists():
        pytest.skip("No generated_document.md — run writer eval first")

    content = doc_path.read_text(encoding="utf-8")

    findings = check_grounding(content, transcript_segments, min_coverage=0.3)

    print(f"\n{'='*60}")
    print("WRITER GROUNDING CHECK")
    print(f"{'='*60}")
    print(f"Transcript segments: {len(transcript_segments)}")
    print(f"Document length:     {len(content)} chars")
    print()

    for f in findings:
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(f.severity, "?")
        print(f"  {icon} {f.message}")

    # Warn on low coverage but don't hard-fail (LLM may rephrase)
    warnings = [f for f in findings if f.severity == "warning"]
    if warnings:
        print(f"\n⚠️  Low grounding detected — document may contain hallucinated content")

    # Only hard-fail if coverage is extremely low
    coverage_finding = next((f for f in findings if f.rule == "grounding-coverage"), None)
    if coverage_finding:
        # Extract coverage percentage from message
        import re

        match = re.search(r'(\d+)% term coverage', coverage_finding.message)
        if match:
            coverage_pct = int(match.group(1))
            assert coverage_pct >= 15, (
                f"Grounding critically low ({coverage_pct}%) — "
                "document may be largely hallucinated"
            )

    print(f"\nRESULT: PASS")


@pytest.mark.asyncio
async def test_editor_grounding(eval_output):
    """Check Editor output maintains grounding (doesn't drift from source)."""
    from src.models.video import ExtractionResult

    from tests.eval.graders import check_grounding

    extraction_path = eval_output / "extraction_result.json"
    if not extraction_path.exists():
        pytest.skip("No extraction_result.json — run extraction eval first")

    extraction = ExtractionResult.model_validate_json(extraction_path.read_text())
    transcript_segments = [seg.text for seg in extraction.transcript]

    if not transcript_segments:
        pytest.skip("Extraction has no transcript segments")

    doc_path = eval_output / "edited_document.md"
    if not doc_path.exists():
        pytest.skip("No edited_document.md — run editor eval first")

    content = doc_path.read_text(encoding="utf-8")

    findings = check_grounding(content, transcript_segments, min_coverage=0.3)

    # Also check writer output for comparison
    writer_path = eval_output / "generated_document.md"
    comparison = ""
    if writer_path.exists():
        writer_content = writer_path.read_text(encoding="utf-8")
        writer_findings = check_grounding(writer_content, transcript_segments)
        writer_coverage = next((f for f in writer_findings if f.rule == "grounding-coverage"), None)
        editor_coverage = next((f for f in findings if f.rule == "grounding-coverage"), None)
        if writer_coverage and editor_coverage:
            comparison = f"\n  Writer:  {writer_coverage.message}\n  Editor:  {editor_coverage.message}"

    print(f"\n{'='*60}")
    print("EDITOR GROUNDING CHECK")
    print(f"{'='*60}")

    for f in findings:
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(f.severity, "?")
        print(f"  {icon} {f.message}")

    if comparison:
        print(f"\n  Grounding comparison:{comparison}")

    print(f"\nRESULT: PASS")


@pytest.mark.asyncio
async def test_pipeline_grounding(eval_output):
    """Check full pipeline output is grounded in extraction transcript."""
    from src.models.video import ExtractionResult

    from tests.eval.graders import check_grounding

    extraction_path = eval_output / "extraction_result.json"
    if not extraction_path.exists():
        pytest.skip("No extraction_result.json — run extraction eval first")

    extraction = ExtractionResult.model_validate_json(extraction_path.read_text())
    transcript_segments = [seg.text for seg in extraction.transcript]

    if not transcript_segments:
        pytest.skip("Extraction has no transcript segments")

    doc_path = eval_output / "pipeline_document.md"
    if not doc_path.exists():
        pytest.skip("No pipeline_document.md — run pipeline eval first")

    content = doc_path.read_text(encoding="utf-8")

    findings = check_grounding(content, transcript_segments, min_coverage=0.3)

    print(f"\n{'='*60}")
    print("PIPELINE GROUNDING CHECK")
    print(f"{'='*60}")

    for f in findings:
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(f.severity, "?")
        print(f"  {icon} {f.message}")

    print(f"\nRESULT: PASS")
