"""Evaluate the Editor Agent with real LLM calls."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


@pytest.mark.asyncio
async def test_editor_agent(eval_output, foundry_client):
    """Test editor agent — refine a document for MS Learn style."""
    from src.agents.editor import EditorAgent
    from src.models.document import GeneratedDocument

    # Try real data, fall back to synthetic
    doc_path = eval_output / "generated_document.json"
    if doc_path.exists():
        document = GeneratedDocument.model_validate_json(doc_path.read_text())
        print("\n[Using real document from previous stage]")
    else:
        from tests.eval.fixtures import make_generated_document

        document = make_generated_document()
        print("\n[Using synthetic document fixture (has intentional style issues)]")

    agent = EditorAgent(foundry_client)

    # First pass: no feedback
    refined = await agent.process(document)

    # Save artifact
    refined_json = eval_output / "edited_document.json"
    refined_json.write_text(refined.model_dump_json(indent=2), encoding="utf-8")
    refined_md = eval_output / "edited_document.md"
    refined_md.write_text(refined.markdown_content, encoding="utf-8")

    # Quality checks
    print(f"\n{'='*60}")
    print("EDITOR AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Original words:  {document.word_count}")
    print(f"Refined words:   {refined.word_count}")
    print(f"Revision:        {refined.revision_number}")
    print(f"Content changed: {document.markdown_content != refined.markdown_content}")

    checks = {
        "Revision incremented": refined.revision_number > document.revision_number,
        "Content not empty": len(refined.markdown_content) > 100,
        "Content not truncated (>50% of original)": refined.word_count > document.word_count * 0.5,
        "Still has frontmatter": refined.markdown_content.strip().startswith("---"),
        "Still has H1": "\n# " in refined.markdown_content or refined.markdown_content.startswith("# "),
    }

    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status} {check}")

    all_passed = all(checks.values())
    print("\nArtifacts:")
    print(f"  JSON: {refined_json}")
    print(f"  MD:   {refined_md}")
    print(f"RESULT: {'PASS' if all_passed else 'WARN'}")

    assert refined.revision_number > document.revision_number, "Revision should be incremented"


@pytest.mark.asyncio
async def test_editor_improves_style_score(foundry_client):
    """Verify editor improves or maintains style compliance score."""
    from src.agents.editor import EditorAgent
    from tests.eval.fixtures import make_generated_document
    from tests.eval.graders import run_all_style_checks

    document = make_generated_document()

    # Score before editing
    before_report = run_all_style_checks(document.markdown_content, document.doc_type.value)
    before_errors = len(before_report.errors)
    before_warnings = len(before_report.warnings)

    # Edit
    agent = EditorAgent(foundry_client)
    refined = await agent.process(document)

    # Score after editing
    after_report = run_all_style_checks(refined.markdown_content, refined.doc_type.value)
    after_errors = len(after_report.errors)
    after_warnings = len(after_report.warnings)

    print(f"Before: {before_errors} errors, {before_warnings} warnings")
    print(f"After:  {after_errors} errors, {after_warnings} warnings")

    # Editor should not make things worse
    assert after_errors <= before_errors, f"Editor increased errors: {before_errors} → {after_errors}"


@pytest.mark.asyncio
async def test_editor_incorporates_feedback(foundry_client):
    """Verify editor addresses specific user feedback."""
    from src.agents.editor import EditorAgent
    from tests.eval.fixtures import make_generated_document

    document = make_generated_document()
    agent = EditorAgent(foundry_client)

    # Provide specific feedback
    feedback = "Please change all instances of 'Repository' to 'repository' (lowercase). Also add a TIP alert after the Clone section suggesting users can also use SSH."

    refined = await agent.process(document, feedback=feedback)
    content = refined.markdown_content

    checks = {
        "Content changed": content != document.markdown_content,
        "Revision incremented": refined.revision_number > document.revision_number,
        "Not truncated": refined.word_count > document.word_count * 0.5,
        "Still has frontmatter": content.strip().startswith("---"),
    }

    # Check feedback was addressed (soft checks)
    feedback_checks = {
        "Reduced uppercase Repository": content.count("Repository") < document.markdown_content.count("Repository"),
        "Added TIP alert": "> [!TIP]" in content or "> [!tip]" in content.lower(),
    }

    for check, passed in {**checks, **feedback_checks}.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    # Hard assert on basics only
    assert checks["Content changed"], "Editor should modify content when given feedback"
    assert checks["Not truncated"], "Editor should not truncate content"


@pytest.mark.asyncio
async def test_editor_no_content_loss(foundry_client):
    """Verify editor doesn't lose sections or significant content."""
    import re

    from src.agents.editor import EditorAgent
    from tests.eval.fixtures import make_generated_document

    document = make_generated_document()

    # Count sections before
    original_h2s = re.findall(r'^## .+$', document.markdown_content, re.MULTILINE)

    agent = EditorAgent(foundry_client)
    refined = await agent.process(document)

    # Count sections after
    refined_h2s = re.findall(r'^## .+$', refined.markdown_content, re.MULTILINE)

    checks = {
        "Same or more H2 sections": len(refined_h2s) >= len(original_h2s),
        "Word count within 20% of original": abs(refined.word_count - document.word_count) / max(document.word_count, 1) < 0.20,
        "Code blocks preserved": refined.markdown_content.count("```") >= document.markdown_content.count("```"),
        "Images preserved": refined.markdown_content.count(":::image") >= document.markdown_content.count(":::image"),
    }

    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    assert checks["Same or more H2 sections"], f"Lost sections: {len(original_h2s)} → {len(refined_h2s)}"
