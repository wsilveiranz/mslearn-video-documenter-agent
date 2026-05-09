"""Evaluate the Writer Agent with real LLM calls."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


@pytest.mark.asyncio
async def test_writer_agent(eval_output, foundry_client):
    """Test writer agent — generate full Markdown document."""
    from src.agents.writer import WriterAgent
    from src.models.document import DocumentOutline
    from src.models.video import ExtractionResult

    # Try real data, fall back to synthetic
    outline_path = eval_output / "document_outline.json"
    extraction_path = eval_output / "extraction_result.json"

    if outline_path.exists():
        outline = DocumentOutline.model_validate_json(outline_path.read_text())
        print("\n[Using real outline from previous stage]")
    else:
        from tests.eval.fixtures import make_document_outline

        outline = make_document_outline()
        print("\n[Using synthetic outline fixture]")

    if extraction_path.exists():
        extraction = ExtractionResult.model_validate_json(extraction_path.read_text())
    else:
        from tests.eval.fixtures import make_extraction_result

        extraction = make_extraction_result()

    agent = WriterAgent(foundry_client)
    document = await agent.process(outline, extraction)

    # Save artifacts
    doc_json_path = eval_output / "generated_document.json"
    doc_json_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
    doc_md_path = eval_output / "generated_document.md"
    doc_md_path.write_text(document.markdown_content, encoding="utf-8")

    # Quality checks
    content = document.markdown_content
    print(f"\n{'='*60}")
    print("WRITER AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Document ID:   {document.document_id}")
    print(f"Word count:    {document.word_count}")
    print(f"Revision:      {document.revision_number}")

    checks = {
        "Has YAML frontmatter": content.startswith("---"),
        "Has title in frontmatter": "title:" in content[:500],
        "Has ms.topic": "ms.topic:" in content[:500] or "ms_topic:" in content[:500],
        "Has H1 heading": "\n# " in content or content.startswith("# "),
        "Has H2 headings": content.count("\n## ") >= 2,
        "Word count > 200": document.word_count > 200,
        "Has image references": ":::image" in content or "![" in content,
        "Has code blocks": "```" in content,
        "No placeholder text": "placeholder" not in content.lower() and "coming in phase" not in content.lower(),
    }

    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status} {check}")

    all_passed = all(checks.values())
    print("\nArtifacts:")
    print(f"  JSON: {doc_json_path}")
    print(f"  MD:   {doc_md_path}")
    print(f"RESULT: {'PASS' if all_passed else 'WARN'}")

    # Show first 500 chars of generated content
    print("\n--- Preview (first 500 chars) ---")
    print(content[:500])
    print("...")

    assert document.word_count > 100, "Document should have substantial content"
    assert "placeholder" not in content.lower(), "Should not contain placeholder text"
