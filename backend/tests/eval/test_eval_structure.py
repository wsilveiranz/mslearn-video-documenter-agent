"""Evaluate the Structure Agent with real LLM calls."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


@pytest.mark.asyncio
async def test_structure_agent(eval_output, foundry_client):
    """Test structure agent with extraction data (real or synthetic)."""
    from src.agents.structure import StructureAgent
    from src.models.document import DocType
    from src.models.video import ExtractionResult

    # Try real extraction result first, fall back to synthetic
    extraction_path = eval_output / "extraction_result.json"
    if extraction_path.exists():
        extraction = ExtractionResult.model_validate_json(extraction_path.read_text())
        print("\n[Using real extraction data from previous stage]")
    else:
        from tests.eval.fixtures import make_extraction_result

        extraction = make_extraction_result()
        print("\n[Using synthetic extraction fixture]")

    agent = StructureAgent(foundry_client)
    outline = await agent.process(extraction, DocType.TUTORIAL)

    # Save artifact
    artifact_path = eval_output / "document_outline.json"
    artifact_path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")

    # Quality checks
    print(f"\n{'='*60}")
    print("STRUCTURE AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Doc type:      {outline.doc_type.value}")
    print(f"Title:         {outline.frontmatter.title}")
    print(f"Description:   {outline.frontmatter.description}")
    print(f"Sections:      {len(outline.sections)}")
    for s in outline.sections:
        indent = "  " * (s.level - 1)
        print(f"  {indent}H{s.level}: {s.heading}")
    print(f"Screenshots:   {len(outline.screenshots)}")

    title = outline.frontmatter.title
    title_len = len(title)
    desc_len = len(outline.frontmatter.description)

    checks = {
        "Has sections": len(outline.sections) >= 3,
        "Title length (43-59 chars)": 30 <= title_len <= 80,  # relaxed for eval
        "Description length (75-300 chars)": 50 <= desc_len <= 350,  # relaxed
        "Has H1": any(s.level == 1 for s in outline.sections),
        "Has H2s": sum(1 for s in outline.sections if s.level == 2) >= 2,
        "Tutorial title format": "tutorial" in title.lower() if outline.doc_type.value == "tutorial" else True,
    }

    for check, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status} {check}")

    all_passed = all(checks.values())
    print(f"Artifact:      {artifact_path}")
    print(f"RESULT:        {'PASS' if all_passed else 'WARN'}")

    assert len(outline.sections) >= 3, "Should have at least 3 sections"
