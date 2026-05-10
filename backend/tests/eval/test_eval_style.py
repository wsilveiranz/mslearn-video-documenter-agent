"""Style compliance evaluation using rule-based graders.

Runs deterministic MS Learn style checks against Writer and Editor output.
No LLM calls — pure regex/rule-based validation.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.style]


def _load_markdown(eval_output, *filenames: str) -> tuple[str, str]:
    """Load the first available markdown file from eval output."""
    for name in filenames:
        path = eval_output / name
        if path.exists():
            return path.read_text(encoding="utf-8"), name
    pytest.skip(f"No document found in eval output. Run writer/editor evals first.")


@pytest.mark.asyncio
async def test_writer_style_compliance(eval_output):
    """Run MS Learn style graders against Writer output."""
    from tests.eval.graders import run_all_style_checks

    content, source = _load_markdown(eval_output, "generated_document.md")
    print(f"\n[Checking style of {source}]")

    report = run_all_style_checks(content, doc_type="tutorial")

    # Print report
    print(f"\n{'='*60}")
    print("WRITER STYLE COMPLIANCE")
    print(f"{'='*60}")
    print(report.summary())
    print()

    for category in ["frontmatter", "headings", "voice", "terminology", "markdown", "structure", "grammar"]:
        cat_findings = report.by_category(category)
        if cat_findings:
            print(f"\n  [{category.upper()}]")
            for f in cat_findings:
                icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(f.severity, "?")
                print(f"    {icon} {f.rule}: {f.message}")

    # Assertions — errors are hard failures
    assert report.passed, (
        f"Style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )

    # Report warning/info counts
    print(f"\nErrors:   {len(report.errors)}")
    print(f"Warnings: {len(report.warnings)}")
    print(f"Info:     {len(report.findings) - len(report.errors) - len(report.warnings)}")
    print(f"RESULT:   {'PASS' if report.passed else 'FAIL'}")


@pytest.mark.asyncio
async def test_editor_style_compliance(eval_output):
    """Run MS Learn style graders against Editor output — should be cleaner than Writer."""
    from tests.eval.graders import run_all_style_checks

    content, source = _load_markdown(eval_output, "edited_document.md")
    print(f"\n[Checking style of {source}]")

    report = run_all_style_checks(content, doc_type="tutorial")

    # Also load writer output for comparison if available
    writer_path = eval_output / "generated_document.md"
    comparison = ""
    if writer_path.exists():
        writer_content = writer_path.read_text(encoding="utf-8")
        writer_report = run_all_style_checks(writer_content, doc_type="tutorial")
        delta_warnings = len(writer_report.warnings) - len(report.warnings)
        comparison = (
            f"\n  vs Writer: {len(writer_report.warnings)} warnings → {len(report.warnings)} warnings"
            f" ({'improved' if delta_warnings > 0 else 'same or worse'})"
        )

    print(f"\n{'='*60}")
    print("EDITOR STYLE COMPLIANCE")
    print(f"{'='*60}")
    print(report.summary())
    if comparison:
        print(comparison)
    print()

    for category in ["frontmatter", "headings", "voice", "terminology", "markdown", "structure", "grammar"]:
        cat_findings = report.by_category(category)
        if cat_findings:
            print(f"\n  [{category.upper()}]")
            for f in cat_findings:
                icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(f.severity, "?")
                print(f"    {icon} {f.rule}: {f.message}")

    assert report.passed, (
        f"Style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )

    print(f"\nErrors:   {len(report.errors)}")
    print(f"Warnings: {len(report.warnings)}")
    print(f"Info:     {len(report.findings) - len(report.errors) - len(report.warnings)}")
    print(f"RESULT:   {'PASS' if report.passed else 'FAIL'}")


@pytest.mark.asyncio
async def test_pipeline_style_compliance(eval_output):
    """Run MS Learn style graders against full pipeline output."""
    from tests.eval.graders import run_all_style_checks

    content, source = _load_markdown(eval_output, "pipeline_document.md")
    print(f"\n[Checking style of {source}]")

    report = run_all_style_checks(content, doc_type="tutorial")

    print(f"\n{'='*60}")
    print("PIPELINE STYLE COMPLIANCE")
    print(f"{'='*60}")
    print(report.summary())
    print()

    for category in ["frontmatter", "headings", "voice", "terminology", "markdown", "structure", "grammar"]:
        cat_findings = report.by_category(category)
        if cat_findings:
            print(f"\n  [{category.upper()}]")
            for f in cat_findings:
                icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(f.severity, "?")
                print(f"    {icon} {f.rule}: {f.message}")

    assert report.passed, (
        f"Style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )

    print(f"\nErrors:   {len(report.errors)}")
    print(f"Warnings: {len(report.warnings)}")
    print(f"Info:     {len(report.findings) - len(report.errors) - len(report.warnings)}")
    print(f"RESULT:   {'PASS' if report.passed else 'FAIL'}")
