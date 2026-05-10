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
