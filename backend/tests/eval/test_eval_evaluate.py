"""Evaluate the Evaluate Agent with real LLM calls."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


@pytest.mark.asyncio
async def test_evaluate_agent(eval_output, foundry_client):
    """Test evaluate agent — score a document on quality dimensions."""
    from src.agents.evaluate import EvaluateAgent
    from src.models.document import GeneratedDocument
    from src.models.video import ExtractionResult

    # Try real data, fall back to synthetic
    doc_path = eval_output / "edited_document.json"
    if not doc_path.exists():
        doc_path = eval_output / "generated_document.json"

    if doc_path.exists():
        document = GeneratedDocument.model_validate_json(doc_path.read_text())
        print(f"\n[Using document from {doc_path.name}]")
    else:
        from tests.eval.fixtures import make_generated_document

        document = make_generated_document()
        print("\n[Using synthetic document fixture]")

    extraction_path = eval_output / "extraction_result.json"
    if extraction_path.exists():
        extraction = ExtractionResult.model_validate_json(extraction_path.read_text())
    else:
        from tests.eval.fixtures import make_extraction_result

        extraction = make_extraction_result()

    agent = EvaluateAgent(foundry_client)
    report = await agent.process(document, extraction)

    # Save artifact
    artifact_path = eval_output / "evaluation_report.json"
    artifact_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # Quality report
    print(f"\n{'='*60}")
    print("EVALUATE AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Document ID:      {report.document_id}")
    print(f"Overall score:    {report.scores.overall:.2f}")
    print(f"Passed:           {'YES' if report.passed else 'NO'}")
    print("\nDimension scores:")
    print(f"  Completeness:     {report.scores.completeness:.2f}")
    print(f"  Accuracy:         {report.scores.accuracy:.2f}")
    print(f"  Style compliance: {report.scores.style_compliance:.2f}")
    print(f"  Readability:      {report.scores.readability:.2f}")
    print(f"\nSuggestions ({len(report.suggestions)}):")
    for s in report.suggestions[:10]:
        print(f"  - [{s.dimension}] {s.issue}: {s.suggestion}")
    print(f"\nSummary: {report.summary}")

    checks = {
        "Scores are in valid range": all(
            0 <= v <= 1
            for v in [
                report.scores.completeness,
                report.scores.accuracy,
                report.scores.style_compliance,
                report.scores.readability,
            ]
        ),
        "Overall > 0 (not default)": report.scores.overall > 0,
        "Has summary": len(report.summary) > 10,
        "Scores not all identical": len(
            {
                report.scores.completeness,
                report.scores.accuracy,
                report.scores.style_compliance,
                report.scores.readability,
            }
        )
        > 1,
    }

    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status} {check}")

    all_passed = all(checks.values())
    print(f"\nArtifact: {artifact_path}")
    print(f"RESULT:   {'PASS' if all_passed else 'WARN'}")

    assert report.scores.overall > 0, "Scores should not all be zero (indicates parsing failure)"
