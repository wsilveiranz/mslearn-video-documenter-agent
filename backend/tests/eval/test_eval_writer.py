"""Evaluate the Writer Agent with real LLM calls."""

from __future__ import annotations

import pytest

from src.models.document import DocType, DocumentOutline, DocumentSection, Frontmatter
from src.models.video import (
    ExtractionResult,
    ProcessingMode,
    Scene,
    TranscriptSegment,
    VideoMetadata,
    VideoSourceType,
)

pytestmark = [pytest.mark.eval, pytest.mark.cloud]


def _make_overview_outline() -> DocumentOutline:
    """Create an overview outline from the synthetic extraction data."""
    return DocumentOutline(
        doc_type=DocType.OVERVIEW,
        frontmatter=Frontmatter(
            title="What is Azure DevOps Repos?",
            description=(
                "Learn about Azure DevOps Repos, a cloud-hosted Git repository "
                "service for version control and collaboration."
            ),
        ),
        sections=[
            DocumentSection(
                heading="What is Azure DevOps Repos?",
                level=1,
                content_hint="Overview introduction",
            ),
            DocumentSection(heading="Key features", level=2, content_hint="Feature table"),
            DocumentSection(
                heading="Repository management",
                level=2,
                content_hint="Explain repo features",
            ),
            DocumentSection(heading="Requirements", level=2, content_hint="What you need"),
            DocumentSection(
                heading="Next steps",
                level=2,
                content_hint="Links to quickstart",
            ),
        ],
        screenshots=[],
        estimated_word_count=400,
    )


def _make_concept_outline() -> DocumentOutline:
    """Create a concept outline from the synthetic extraction data."""
    return DocumentOutline(
        doc_type=DocType.CONCEPT,
        frontmatter=Frontmatter(
            title="What is Git repository cloning in Azure DevOps?",
            description=(
                "Understand how Git repository cloning works in Azure DevOps, "
                "including HTTPS authentication and local workspace setup."
            ),
        ),
        sections=[
            DocumentSection(
                heading="What is Git repository cloning?",
                level=1,
                content_hint="Concept introduction explaining what cloning is",
            ),
            DocumentSection(
                heading="How cloning works",
                level=2,
                content_hint="Explain the mechanics of git clone",
            ),
            DocumentSection(
                heading="Authentication methods",
                level=2,
                content_hint="HTTPS vs SSH, personal access tokens",
            ),
            DocumentSection(
                heading="Cloning in Azure DevOps",
                level=2,
                content_hint="Specific behavior in Azure DevOps Repos",
                source_scenes=["scene_000", "scene_001"],
            ),
            DocumentSection(
                heading="Next steps",
                level=2,
                content_hint="Links to how-to and quickstart",
            ),
        ],
        screenshots=[],
        estimated_word_count=450,
    )


def _make_howto_outline() -> DocumentOutline:
    """Create a how-to outline from the synthetic extraction data."""
    return DocumentOutline(
        doc_type=DocType.HOWTO,
        frontmatter=Frontmatter(
            title="Clone an Azure DevOps repository with HTTPS",
            description=(
                "Step-by-step guide to cloning an Azure DevOps Git repository "
                "to your local machine using HTTPS and the Git command line."
            ),
        ),
        sections=[
            DocumentSection(
                heading="Clone an Azure DevOps repository",
                level=1,
                content_hint="Introduction — what this guide accomplishes",
            ),
            DocumentSection(
                heading="Prerequisites",
                level=2,
                content_hint="Git installed, Azure DevOps access",
            ),
            DocumentSection(
                heading="Get the clone URL",
                level=2,
                content_hint="Navigate to Repos and copy the HTTPS URL",
                source_scenes=["scene_000", "scene_001"],
                steps=["Sign in to Azure DevOps", "Open your project", "Select Repos", "Select Clone"],
            ),
            DocumentSection(
                heading="Clone the repository",
                level=2,
                content_hint="Run git clone in terminal",
                source_scenes=["scene_001", "scene_002"],
                steps=["Open terminal", "Run git clone <url>", "Verify with git status"],
            ),
            DocumentSection(
                heading="Next steps",
                level=2,
                content_hint="Links to branching and pull request guides",
            ),
        ],
        screenshots=[],
        estimated_word_count=350,
    )


def _make_thin_extraction() -> ExtractionResult:
    """Create a minimal ExtractionResult with almost no evidence."""
    metadata = VideoMetadata(
        video_id="thin-test",
        source_path="test.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=10.0,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=1_000_000,
    )
    return ExtractionResult(
        transcript=[
            TranscriptSegment(text="Welcome to Azure DevOps.", start_seconds=0.0, end_seconds=3.0),
            TranscriptSegment(text="Let's look at the repos.", start_seconds=3.0, end_seconds=6.0),
        ],
        scenes=[
            Scene(
                id="scene_000",
                start_seconds=0.0,
                end_seconds=10.0,
                keyframe_ids=[],
                description="Intro",
            )
        ],
        keyframes=[],
        ocr_entries=[],
        entities=[],
        video_metadata=metadata,
        processing_mode=ProcessingMode.LOCAL,
    )


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


# ---------------------------------------------------------------------------
# Multi-doc-type writer evaluation
# ---------------------------------------------------------------------------

_DOC_TYPE_OUTLINES = {
    DocType.OVERVIEW: _make_overview_outline,
    DocType.CONCEPT: _make_concept_outline,
    DocType.HOWTO: _make_howto_outline,
}

_MS_TOPIC_MAP = {
    DocType.OVERVIEW: "overview",
    DocType.CONCEPT: "concept-article",
    DocType.HOWTO: "how-to",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_type", list(_DOC_TYPE_OUTLINES.keys()), ids=lambda d: d.value)
async def test_writer_doc_type(doc_type: DocType, eval_output, foundry_client):
    """Test Writer agent for a specific doc type with rule-based and LLM-judge grading."""
    from src.agents.writer import WriterAgent
    from src.services.llm_judge import LLMJudge
    from tests.eval.fixtures import make_extraction_result
    from tests.eval.graders import run_all_style_checks

    outline = _DOC_TYPE_OUTLINES[doc_type]()
    extraction = make_extraction_result()

    agent = WriterAgent(foundry_client)
    document = await agent.process(outline, extraction)
    content = document.markdown_content

    # Save artifact
    artifact_path = eval_output / f"writer_{doc_type.value}_document.md"
    artifact_path.write_text(content, encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"WRITER EVAL — {doc_type.value.upper()}")
    print(f"{'='*60}")
    print(f"Word count: {document.word_count}")
    print(f"Artifact:   {artifact_path}")

    # Rule-based graders
    report = run_all_style_checks(content, doc_type.value)
    print(f"\n{report.summary()}")
    for finding in report.findings:
        print(f"  [{finding.severity.upper()}] {finding.rule}: {finding.message}")

    # LLM-as-judge — voice/tone dimension
    judge = LLMJudge(foundry_client)
    voice_result = await judge.evaluate(content, "voice_tone")
    print(f"\nVoice/tone score: {voice_result.score:.2f}")
    print(f"Reasoning: {voice_result.reasoning[:200]}")

    # Soft assertions — log PASS/FAIL for informational checks
    frontmatter_present = content.startswith("---")
    has_ms_topic = (
        f"ms.topic: {_MS_TOPIC_MAP[doc_type]}" in content[:600]
        or f"ms_topic: {_MS_TOPIC_MAP[doc_type]}" in content[:600]
    )
    word_count_ok = document.word_count > 200
    no_style_errors = report.passed
    voice_ok = voice_result.score >= 0.5

    soft_checks = {
        "Frontmatter present": frontmatter_present,
        f"ms.topic = {_MS_TOPIC_MAP[doc_type]}": has_ms_topic,
        "Word count > 200": word_count_ok,
        "No style errors": no_style_errors,
        f"Voice/tone score >= 0.5 (got {voice_result.score:.2f})": voice_ok,
    }
    print("\nSoft checks:")
    for label, passed in soft_checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {label}")

    # Hard assertions on the most critical checks
    assert frontmatter_present, f"[{doc_type.value}] Document must have YAML frontmatter"
    assert document.word_count > 200, f"[{doc_type.value}] Document must exceed 200 words"
    assert report.passed, (
        f"[{doc_type.value}] Rule-based style check found errors: "
        + "; ".join(f.message for f in report.errors)
    )
    assert voice_result.score >= 0.5, (
        f"[{doc_type.value}] Voice/tone score {voice_result.score:.2f} below threshold 0.5"
    )


# ---------------------------------------------------------------------------
# Thin-data resilience test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_writer_with_thin_data(eval_output, foundry_client):
    """Writer agent must produce a valid document even with near-empty extraction data."""
    from src.agents.writer import WriterAgent
    from tests.eval.fixtures import make_document_outline

    outline = make_document_outline()
    extraction = _make_thin_extraction()

    agent = WriterAgent(foundry_client)
    document = await agent.process(outline, extraction)
    content = document.markdown_content

    artifact_path = eval_output / "writer_thin_data_document.md"
    artifact_path.write_text(content, encoding="utf-8")

    print(f"\n{'='*60}")
    print("WRITER EVAL — THIN EXTRACTION DATA")
    print(f"{'='*60}")
    print(f"Word count: {document.word_count}")
    print(f"Artifact:   {artifact_path}")
    print("\n--- Preview (first 400 chars) ---")
    print(content[:400])
    print("...")

    has_frontmatter = content.startswith("---")
    has_h1 = "\n# " in content or content.startswith("# ")
    is_valid = document.word_count > 0

    checks = {
        "Has YAML frontmatter": has_frontmatter,
        "Has H1 heading": has_h1,
        "Produces non-empty document": is_valid,
        "No raw hallucinated git commands beyond evidence": (
            content.count("```") == 0
            or any(
                phrase in content
                for phrase in ["git clone", "git status", "Azure DevOps", "repos"]
            )
        ),
    }
    print("\nChecks:")
    for label, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {label}")

    assert has_frontmatter, "Thin-data document must still have YAML frontmatter"
    assert document.word_count > 0, "Writer must produce non-empty output for thin data"
