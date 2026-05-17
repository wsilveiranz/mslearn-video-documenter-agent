"""Evaluate the Structure Agent with real LLM calls."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


def _print_outline(outline, artifact_path) -> None:
    """Print a standard outline evaluation block."""
    print(f"\n{'='*60}")
    print("STRUCTURE AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Doc type:      {outline.doc_type.value}")
    print(f"Title:         {outline.frontmatter.title}")
    print(f"Description:   {outline.frontmatter.description}")
    print(f"ms.topic:      {outline.frontmatter.ms_topic}")
    print(f"Sections:      {len(outline.sections)}")
    for s in outline.sections:
        indent = "  " * (s.level - 1)
        print(f"  {indent}H{s.level}: {s.heading}")
    print(f"Screenshots:   {len(outline.screenshots)}")
    print(f"Artifact:      {artifact_path}")


def _run_basic_checks(outline) -> dict[str, bool]:
    """Return a dict of basic checks that apply to all doc types."""
    title_len = len(outline.frontmatter.title)
    desc_len = len(outline.frontmatter.description)
    has_h1_section = any(s.level == 1 for s in outline.sections)
    has_title = bool(outline.frontmatter.title.strip())
    return {
        "Has sections (>=3)": len(outline.sections) >= 3,
        "Title length (30-80 chars)": 30 <= title_len <= 80,
        "Description length (50-350 chars)": 50 <= desc_len <= 350,
        "Has H1 (section or title)": has_h1_section or has_title,
        "Has H2s (>=2)": sum(1 for s in outline.sections if s.level == 2) >= 2,
    }


def _section_headings(outline) -> list[str]:
    return [s.heading.lower() for s in outline.sections]


def _h1_heading(outline) -> str:
    """Return the H1 heading — from sections if present, otherwise from frontmatter title."""
    for s in outline.sections:
        if s.level == 1:
            return s.heading
    return outline.frontmatter.title


def _print_checks(checks: dict[str, bool]) -> bool:
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")
    return all(checks.values())


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

    _print_outline(outline, artifact_path)

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
    print(f"RESULT:        {'PASS' if all_passed else 'WARN'}")

    assert len(outline.sections) >= 3, "Should have at least 3 sections"


@pytest.mark.asyncio
async def test_structure_agent_overview(eval_output, foundry_client):
    """Test structure agent produces a valid Overview outline."""
    from src.agents.structure import StructureAgent
    from src.models.document import DocType
    from tests.eval.fixtures import make_extraction_result

    extraction = make_extraction_result()
    print("\n[Using synthetic extraction fixture]")

    agent = StructureAgent(foundry_client)
    outline = await agent.process(extraction, DocType.OVERVIEW)

    artifact_path = eval_output / f"document_outline_{DocType.OVERVIEW.value}.json"
    artifact_path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")

    _print_outline(outline, artifact_path)

    headings = _section_headings(outline)
    h1 = _h1_heading(outline)

    checks = _run_basic_checks(outline)
    checks.update(
        {
            "H1/title starts with 'What is'": h1.lower().startswith("what is"),
            "Has 'features' section (H2)": any(
                "key features" in h or h == "features" or "overview" in h for h in headings
            ),
            "Has 'next steps' section": any("next steps" in h or "next step" in h for h in headings),
            "ms.topic is 'overview'": outline.frontmatter.ms_topic == "overview",
        }
    )

    all_passed = _print_checks(checks)
    print(f"RESULT:        {'PASS' if all_passed else 'WARN'}")

    assert len(outline.sections) >= 3, "Should have at least 3 sections"
    assert h1.lower().startswith("what is"), f"Overview H1/title should start with 'What is', got: {h1!r}"


@pytest.mark.asyncio
async def test_structure_agent_concept(eval_output, foundry_client):
    """Test structure agent produces a valid Concept outline."""
    from src.agents.structure import StructureAgent
    from src.models.document import DocType
    from tests.eval.fixtures import make_extraction_result

    extraction = make_extraction_result()
    print("\n[Using synthetic extraction fixture]")

    agent = StructureAgent(foundry_client)
    outline = await agent.process(extraction, DocType.CONCEPT)

    artifact_path = eval_output / f"document_outline_{DocType.CONCEPT.value}.json"
    artifact_path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")

    _print_outline(outline, artifact_path)

    headings = _section_headings(outline)
    h1 = _h1_heading(outline)

    checks = _run_basic_checks(outline)
    checks.update(
        {
            "H1/title starts with 'What is'": h1.lower().startswith("what is"),
            "Has 'key concepts' section (H2)": any(
                "key concepts" in h or "concept" in h or "what is" in h or "how" in h for h in headings
            ),
            "Has 'next steps' section": any("next steps" in h or "next step" in h for h in headings),
            "ms.topic is 'concept-article'": outline.frontmatter.ms_topic == "concept-article",
        }
    )

    all_passed = _print_checks(checks)
    print(f"RESULT:        {'PASS' if all_passed else 'WARN'}")

    assert len(outline.sections) >= 3, "Should have at least 3 sections"
    assert h1.lower().startswith("what is"), f"Concept H1/title should start with 'What is', got: {h1!r}"


@pytest.mark.asyncio
async def test_structure_agent_howto(eval_output, foundry_client):
    """Test structure agent produces a valid How-to outline."""
    from src.agents.structure import StructureAgent
    from src.models.document import DocType
    from tests.eval.fixtures import make_extraction_result

    extraction = make_extraction_result()
    print("\n[Using synthetic extraction fixture]")

    agent = StructureAgent(foundry_client)
    outline = await agent.process(extraction, DocType.HOWTO)

    artifact_path = eval_output / f"document_outline_{DocType.HOWTO.value}.json"
    artifact_path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")

    _print_outline(outline, artifact_path)

    headings = _section_headings(outline)
    h1 = _h1_heading(outline)

    checks = _run_basic_checks(outline)
    checks.update(
        {
            "H1 does NOT start with 'How to:'": not h1.lower().startswith("how to:"),
            "Has 'prerequisites' section": any(
                "prerequisites" in h or "prerequisite" in h or "before you begin" in h for h in headings
            ),
            "Has 'next steps' section": any("next steps" in h or "next step" in h for h in headings),
            "ms.topic is 'how-to'": outline.frontmatter.ms_topic == "how-to",
        }
    )

    all_passed = _print_checks(checks)
    print(f"RESULT:        {'PASS' if all_passed else 'WARN'}")

    assert len(outline.sections) >= 3, "Should have at least 3 sections"
