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

    # Print rubric appendix
    if report.rubric_appendix:
        print(f"\n{'─'*60}")
        print("RUBRIC APPENDIX")
        print(f"{'─'*60}")
        for ra in report.rubric_appendix:
            print(f"\n  [{ra.dimension}] score={ra.score:.2f}")
            if ra.reasoning:
                print(f"    Reasoning: {ra.reasoning[:200]}")
            if ra.strengths:
                print(f"    Strengths:")
                for s in ra.strengths[:3]:
                    print(f"      + {s}")
            if ra.gaps:
                print(f"    Gaps:")
                for g in ra.gaps[:3]:
                    print(f"      - {g}")
            if ra.evidence:
                print(f"    Evidence:")
                for e in ra.evidence[:3]:
                    print(f"      • {e}")
    else:
        print("\n  (No rubric appendix returned)")

    checks = {
        "Scores are in valid range":all(
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


# ---------------------------------------------------------------------------
# Known-good document fixture
# ---------------------------------------------------------------------------

_KNOWN_GOOD_DOC_MARKDOWN = '''---
title: "Configure custom domains for Azure App Service"
description: "Learn how to map a custom DNS domain name to your Azure App Service web app using the Azure portal."
author: video-documenter
ms.author: video-documenter
ms.date: 05/17/2026
ms.topic: how-to
ms.service: azure-app-service
ms.custom: ai-assisted
# Customer intent: As a developer, I want to configure a custom domain so that my app has a professional URL.
---

# Configure custom domains for Azure App Service

This article shows you how to map a custom domain name to your Azure App Service web app.

## Prerequisites

- An Azure account with an active subscription. [Create one for free](https://azure.microsoft.com/free/).
- An App Service web app. If you don't have one, [create one](create-web-app.md).
- A custom domain name. If you don't have one, [buy a domain](buy-domain.md).

## Map a custom domain

1. Sign in to the [Azure portal](https://portal.azure.com).
1. Navigate to your App Service app.
1. In the left menu, select **Custom domains**.
1. Select **Add custom domain**.
1. In the **Domain** field, enter your custom domain name.
1. Select **Validate**.
1. Add the DNS records shown in the validation results to your domain provider.
1. Select **Add**.

:::image type="content" source="./media/custom-domain-config.png" alt-text="Azure portal showing the custom domains configuration pane with the Add custom domain dialog":::

> [!NOTE]
> DNS propagation can take up to 48 hours. If validation fails, wait and try again.

## Verify the mapping

1. Open a browser and navigate to your custom domain.
1. Verify that your app loads correctly.

## Next steps

- [Secure a custom domain with TLS/SSL](secure-custom-domain.md)
- [Scale up your App Service plan](scale-up.md)
'''

# ---------------------------------------------------------------------------
# Known-bad document fixture (intentional quality issues)
# ---------------------------------------------------------------------------

_KNOWN_BAD_DOC_MARKDOWN = '''---
title: "Configuring Custom Domains"
author: video-documenter
ms.author: video-documenter
ms.date: 05/17/2026
ms.custom: ai-assisted
---

# Configuring Custom Domains

This document explains how to log in to the Azure Portal and configure a Custom Domain for
your App Service application with many unnecessary steps.

## Step 1: Initial Setup And Preparation

1. Log in to the Azure portal at https://portal.azure.com.
1. Click on All Services in the left navigation pane.
1. Search for App Services in the search bar.
1. Click on App Services to view all your applications.
1. Select the application you want to configure from the list.
1. Wait for the application overview blade to load completely.
1. Click on Settings in the left menu to expand it.
1. Scroll down to find the Custom Domains option.
1. Click on Custom Domains to open the configuration pane.
1. Review the current domain assignments on the page.
1. Take note of the IP address shown in the Custom Domains pane.
1. Open a new browser tab to access your domain registrar.
1. Navigate to the DNS management section of your registrar.

## Step 2: DNS Configuration

![Custom domain settings](portal-screenshot.png)

1. In your domain registrar's DNS settings, create an A record.
1. Set the A record to point to the IP address you noted earlier.
1. Optionally, create a CNAME record for the www subdomain.
1. Save the DNS changes in your registrar.
1. Return to the Azure portal tab.
1. Enter your custom domain name in the Domain field.
1. Click Validate to check DNS propagation status.
1. Wait several hours for DNS changes to propagate globally across all nameservers.
1. Re-validate if the first attempt fails due to propagation delays.
1. Once validated, click Add Binding to complete the configuration.
1. Configure SSL certificate from Azure managed certificates or bring your own certificate.
1. Set the TLS/SSL binding type to SNI SSL or IP Based SSL.
1. Click Add Binding again to save the SSL configuration alongside domain binding.
1. Navigate to the Overview blade of your App Service to see the new custom domain.

## Step 3: Advanced Verification And Troubleshooting Procedures

1. Run nslookup on your custom domain to verify DNS resolution.
1. Use curl to test HTTP and HTTPS connectivity to the new domain.
1. Deploy a test endpoint to your application to confirm routing.
1. Check application logs in Log Stream to verify incoming requests.
1. Monitor for any certificate errors using browser developer tools.
'''


def _make_good_extraction() -> "ExtractionResult":
    """Extraction result whose transcript mirrors the known-good document steps."""
    from src.models.video import (
        ExtractionResult,
        Keyframe,
        OCREntry,
        ProcessingMode,
        Scene,
        TranscriptSegment,
        VideoMetadata,
        VideoSourceType,
    )

    metadata = VideoMetadata(
        video_id="eval-good-001",
        source_path="test_videos/custom-domain-demo.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=60.0,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=6_000_000,
    )

    transcript = [
        TranscriptSegment(
            text="In this video I'll show you how to configure a custom domain for your Azure App Service web app.",
            start_seconds=0.0,
            end_seconds=5.0,
        ),
        TranscriptSegment(
            text="Sign in to the Azure portal and navigate to your App Service app.",
            start_seconds=5.5,
            end_seconds=9.0,
        ),
        TranscriptSegment(
            text="In the left menu, select Custom domains.",
            start_seconds=9.5,
            end_seconds=12.0,
        ),
        TranscriptSegment(
            text="Select Add custom domain to open the dialog.",
            start_seconds=12.5,
            end_seconds=15.0,
        ),
        TranscriptSegment(
            text="In the Domain field, enter your custom domain name then select Validate.",
            start_seconds=15.5,
            end_seconds=19.0,
        ),
        TranscriptSegment(
            text="Add the DNS records shown to your domain provider.",
            start_seconds=19.5,
            end_seconds=22.5,
        ),
        TranscriptSegment(
            text="Select Add to complete the mapping.",
            start_seconds=23.0,
            end_seconds=25.5,
        ),
        TranscriptSegment(
            text="Now open a browser, navigate to your custom domain, and verify your app loads correctly.",
            start_seconds=26.0,
            end_seconds=31.0,
        ),
    ]

    scenes = [
        Scene(
            id="scene_000",
            start_seconds=0.0,
            end_seconds=12.0,
            keyframe_ids=["kf_000", "kf_001"],
            description="Azure portal App Service overview and Custom domains menu",
        ),
        Scene(
            id="scene_001",
            start_seconds=12.0,
            end_seconds=26.0,
            keyframe_ids=["kf_002", "kf_003"],
            description="Add custom domain dialog and validation",
        ),
        Scene(
            id="scene_002",
            start_seconds=26.0,
            end_seconds=31.0,
            keyframe_ids=["kf_004"],
            description="Browser verification of custom domain",
        ),
    ]

    keyframes = [
        Keyframe(
            id="kf_000",
            timestamp_seconds=3.0,
            image_path="frames/frame_001.png",
            ui_description="Azure portal showing App Service overview blade.",
            scene_id="scene_000",
        ),
        Keyframe(
            id="kf_001",
            timestamp_seconds=10.0,
            image_path="frames/frame_002.png",
            ui_description="App Service left menu with Custom domains option highlighted.",
            scene_id="scene_000",
        ),
        Keyframe(
            id="kf_002",
            timestamp_seconds=14.0,
            image_path="frames/frame_003.png",
            ui_description="Add custom domain dialog with Domain field and Validate button.",
            scene_id="scene_001",
        ),
        Keyframe(
            id="kf_003",
            timestamp_seconds=20.0,
            image_path="frames/frame_004.png",
            ui_description="DNS records table shown in the custom domain validation results.",
            scene_id="scene_001",
        ),
        Keyframe(
            id="kf_004",
            timestamp_seconds=28.0,
            image_path="frames/frame_005.png",
            ui_description="Browser displaying the app successfully loaded on the custom domain.",
            scene_id="scene_002",
        ),
    ]

    ocr_entries = [
        OCREntry(text="Custom domains", timestamp_seconds=10.0),
        OCREntry(text="Add custom domain", timestamp_seconds=13.0),
        OCREntry(text="Validate", timestamp_seconds=16.0),
        OCREntry(text="Add", timestamp_seconds=24.0),
    ]

    return ExtractionResult(
        transcript=transcript,
        scenes=scenes,
        keyframes=keyframes,
        ocr_entries=ocr_entries,
        entities=[],
        video_metadata=metadata,
        processing_mode=ProcessingMode.LOCAL,
    )


def _make_good_document() -> "GeneratedDocument":
    from src.models.document import DocType, DocumentOutline, DocumentSection, Frontmatter, GeneratedDocument

    outline = DocumentOutline(
        doc_type=DocType.HOWTO,
        frontmatter=Frontmatter(
            title="Configure custom domains for Azure App Service",
            description="Learn how to map a custom DNS domain name to your Azure App Service web app using the Azure portal.",
            author="video-documenter",
            **{"ms.author": "video-documenter", "ms.date": "05/17/2026", "ms.topic": "how-to", "ms.service": "azure-app-service"},
        ),
        sections=[
            DocumentSection(heading="Configure custom domains for Azure App Service", level=1, content_hint="Introduction"),
            DocumentSection(heading="Prerequisites", level=2, content_hint="Required resources"),
            DocumentSection(heading="Map a custom domain", level=2, content_hint="Step-by-step mapping", source_scenes=["scene_000", "scene_001"]),
            DocumentSection(heading="Verify the mapping", level=2, content_hint="Verify in browser", source_scenes=["scene_002"]),
            DocumentSection(heading="Next steps", level=2, content_hint="Related articles"),
        ],
        screenshots=[],
        estimated_word_count=300,
    )
    return GeneratedDocument(
        document_id="eval-good-001",
        doc_type=DocType.HOWTO,
        outline=outline,
        markdown_content=_KNOWN_GOOD_DOC_MARKDOWN,
        media_files=[],
        word_count=len(_KNOWN_GOOD_DOC_MARKDOWN.split()),
        revision_number=1,
    )


def _make_bad_document() -> "GeneratedDocument":
    from src.models.document import DocType, DocumentOutline, DocumentSection, Frontmatter, GeneratedDocument

    outline = DocumentOutline(
        doc_type=DocType.HOWTO,
        frontmatter=Frontmatter(
            title="Configuring Custom Domains",
            description="Configure custom domains.",
            author="video-documenter",
            **{"ms.author": "video-documenter", "ms.date": "05/17/2026", "ms.topic": "", "ms.service": ""},
        ),
        sections=[
            DocumentSection(heading="Configuring Custom Domains", level=1, content_hint="Introduction"),
        ],
        screenshots=[],
        estimated_word_count=400,
    )
    return GeneratedDocument(
        document_id="eval-bad-001",
        doc_type=DocType.HOWTO,
        outline=outline,
        markdown_content=_KNOWN_BAD_DOC_MARKDOWN,
        media_files=[],
        word_count=len(_KNOWN_BAD_DOC_MARKDOWN.split()),
        revision_number=1,
    )


@pytest.mark.asyncio
async def test_evaluate_known_good_document(eval_output, foundry_client):
    """Evaluate agent should give a passing score to a well-crafted MS Learn document."""
    from src.agents.evaluate import EvaluateAgent

    document = _make_good_document()
    extraction = _make_good_extraction()

    agent = EvaluateAgent(foundry_client)
    report = await agent.process(document, extraction)

    artifact_path = eval_output / "evaluation_report_good.json"
    artifact_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print("KNOWN-GOOD DOCUMENT EVALUATION")
    print(f"{'='*60}")
    print(f"Overall score:      {report.scores.overall:.2f}")
    print(f"Passed:             {'YES' if report.passed else 'NO'}")
    print(f"Completeness:       {report.scores.completeness:.2f}")
    print(f"Accuracy:           {report.scores.accuracy:.2f}")
    print(f"Style compliance:   {report.scores.style_compliance:.2f}")
    print(f"Readability:        {report.scores.readability:.2f}")
    print(f"Suggestions ({len(report.suggestions)}):")
    for s in report.suggestions[:5]:
        print(f"  - [{s.dimension}] {s.issue}: {s.suggestion}")
    print(f"Summary: {report.summary}")

    # Print rubric appendix
    if report.rubric_appendix:
        print(f"\n{'─'*60}")
        print("RUBRIC APPENDIX")
        print(f"{'─'*60}")
        for ra in report.rubric_appendix:
            print(f"\n  [{ra.dimension}] score={ra.score:.2f}")
            if ra.reasoning:
                print(f"    Reasoning: {ra.reasoning[:200]}")
            if ra.strengths:
                print(f"    Strengths:")
                for s in ra.strengths[:3]:
                    print(f"      + {s}")
            if ra.gaps:
                print(f"    Gaps:")
                for g in ra.gaps[:3]:
                    print(f"      - {g}")
            if ra.evidence:
                print(f"    Evidence:")
                for e in ra.evidence[:3]:
                    print(f"      • {e}")
    else:
        print("\n  (No rubric appendix returned)")

    checks = {
        "report.passed is True OR overall >= 0.7":report.passed or report.scores.overall >= 0.7,
        "overall >= 0.7": report.scores.overall >= 0.7,
        "completeness >= 0.5": report.scores.completeness >= 0.5,
        "accuracy >= 0.5": report.scores.accuracy >= 0.5,
        "style_compliance >= 0.5": report.scores.style_compliance >= 0.5,
        "readability >= 0.5": report.scores.readability >= 0.5,
    }

    print("\nChecks:")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    print(f"Artifact: {artifact_path}")

    assert report.passed or report.scores.overall >= 0.7, (
        f"Known-good document should pass or score >= 0.7, got {report.scores.overall:.2f}"
    )
    assert all(
        score >= 0.5
        for score in [
            report.scores.completeness,
            report.scores.accuracy,
            report.scores.style_compliance,
            report.scores.readability,
        ]
    ), (
        f"All dimension scores should be >= 0.5 for known-good doc. "
        f"Got: completeness={report.scores.completeness:.2f}, "
        f"accuracy={report.scores.accuracy:.2f}, "
        f"style={report.scores.style_compliance:.2f}, "
        f"readability={report.scores.readability:.2f}"
    )


@pytest.mark.asyncio
async def test_evaluate_known_bad_document(eval_output, foundry_client):
    """Evaluate agent should flag a document with intentional quality issues."""
    from src.agents.evaluate import EvaluateAgent

    document = _make_bad_document()
    extraction = _make_good_extraction()  # same source — makes ungrounded steps detectable

    agent = EvaluateAgent(foundry_client)
    report = await agent.process(document, extraction)

    artifact_path = eval_output / "evaluation_report_bad.json"
    artifact_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print("KNOWN-BAD DOCUMENT EVALUATION")
    print(f"{'='*60}")
    print(f"Overall score:      {report.scores.overall:.2f}")
    print(f"Passed:             {'YES' if report.passed else 'NO'}")
    print(f"Completeness:       {report.scores.completeness:.2f}")
    print(f"Accuracy:           {report.scores.accuracy:.2f}")
    print(f"Style compliance:   {report.scores.style_compliance:.2f}")
    print(f"Readability:        {report.scores.readability:.2f}")
    print(f"Suggestions ({len(report.suggestions)}):")
    for s in report.suggestions[:10]:
        print(f"  - [{s.dimension}] {s.issue}: {s.suggestion}")
    print(f"Summary: {report.summary}")

    # Print rubric appendix
    if report.rubric_appendix:
        print(f"\n{'─'*60}")
        print("RUBRIC APPENDIX")
        print(f"{'─'*60}")
        for ra in report.rubric_appendix:
            print(f"\n  [{ra.dimension}] score={ra.score:.2f}")
            if ra.reasoning:
                print(f"    Reasoning: {ra.reasoning[:200]}")
            if ra.strengths:
                print(f"    Strengths:")
                for s in ra.strengths[:3]:
                    print(f"      + {s}")
            if ra.gaps:
                print(f"    Gaps:")
                for g in ra.gaps[:3]:
                    print(f"      - {g}")
            if ra.evidence:
                print(f"    Evidence:")
                for e in ra.evidence[:3]:
                    print(f"      • {e}")
    else:
        print("\n  (No rubric appendix returned)")

    checks = {
        "not passed OR overall < 0.7":not report.passed or report.scores.overall < 0.7,
        "has suggestions (agent identified issues)": len(report.suggestions) > 0,
    }

    print("\nChecks:")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    print(f"Artifact: {artifact_path}")

    assert not report.passed or report.scores.overall < 0.7, (
        f"Known-bad document should not pass or should score < 0.7, got overall={report.scores.overall:.2f}, passed={report.passed}"
    )
    assert len(report.suggestions) > 0, "Evaluate agent should produce suggestions for a document with known issues"


@pytest.mark.asyncio
async def test_evaluate_score_differential(eval_output, foundry_client):
    """Good document should score meaningfully higher than bad document (≥ 0.15 overall differential)."""
    from src.agents.evaluate import EvaluateAgent

    good_doc = _make_good_document()
    bad_doc = _make_bad_document()
    extraction = _make_good_extraction()

    agent = EvaluateAgent(foundry_client)

    good_report = await agent.process(good_doc, extraction)
    bad_report = await agent.process(bad_doc, extraction)

    good_path = eval_output / "evaluation_report_good_diff.json"
    bad_path = eval_output / "evaluation_report_bad_diff.json"
    good_path.write_text(good_report.model_dump_json(indent=2), encoding="utf-8")
    bad_path.write_text(bad_report.model_dump_json(indent=2), encoding="utf-8")

    diff_overall = good_report.scores.overall - bad_report.scores.overall
    diff_completeness = good_report.scores.completeness - bad_report.scores.completeness
    diff_accuracy = good_report.scores.accuracy - bad_report.scores.accuracy
    diff_style = good_report.scores.style_compliance - bad_report.scores.style_compliance
    diff_readability = good_report.scores.readability - bad_report.scores.readability

    print(f"\n{'='*60}")
    print("SCORE DIFFERENTIAL (good minus bad)")
    print(f"{'='*60}")
    print(f"{'Dimension':<22} {'Good':>6} {'Bad':>6} {'Diff':>7}")
    print(f"{'-'*45}")
    print(f"{'Overall':<22} {good_report.scores.overall:>6.2f} {bad_report.scores.overall:>6.2f} {diff_overall:>+7.2f}")
    print(f"{'Completeness':<22} {good_report.scores.completeness:>6.2f} {bad_report.scores.completeness:>6.2f} {diff_completeness:>+7.2f}")
    print(f"{'Accuracy':<22} {good_report.scores.accuracy:>6.2f} {bad_report.scores.accuracy:>6.2f} {diff_accuracy:>+7.2f}")
    print(f"{'Style compliance':<22} {good_report.scores.style_compliance:>6.2f} {bad_report.scores.style_compliance:>6.2f} {diff_style:>+7.2f}")
    print(f"{'Readability':<22} {good_report.scores.readability:>6.2f} {bad_report.scores.readability:>6.2f} {diff_readability:>+7.2f}")

    dimension_diffs = [diff_completeness, diff_accuracy, diff_style, diff_readability]
    majority_higher = sum(1 for d in dimension_diffs if d > 0)

    checks = {
        "good overall > bad overall": good_report.scores.overall > bad_report.scores.overall,
        "overall differential >= 0.15": diff_overall >= 0.15,
        "good scores higher in majority of dimensions": majority_higher >= 3,
    }

    print("\nChecks:")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    assert good_report.scores.overall > bad_report.scores.overall, (
        f"Good document should score higher than bad document overall. "
        f"Good={good_report.scores.overall:.2f}, Bad={bad_report.scores.overall:.2f}"
    )
    assert diff_overall >= 0.15, (
        f"Score differential should be >= 0.15. Got {diff_overall:.2f} "
        f"(Good={good_report.scores.overall:.2f}, Bad={bad_report.scores.overall:.2f})"
    )
    assert majority_higher >= 3, (
        f"Good document should score higher in at least 3 of 4 dimensions. "
        f"Higher in {majority_higher}/4: completeness={diff_completeness:+.2f}, "
        f"accuracy={diff_accuracy:+.2f}, style={diff_style:+.2f}, readability={diff_readability:+.2f}"
    )


@pytest.mark.asyncio
async def test_evaluate_rubric_appendix_structure(eval_output, foundry_client):
    """Evaluate agent should return a rubric appendix with per-dimension reasoning."""
    from src.agents.evaluate import EvaluateAgent

    document = _make_good_document()
    extraction = _make_good_extraction()

    agent = EvaluateAgent(foundry_client)
    report = await agent.process(document, extraction)

    artifact_path = eval_output / "evaluation_report_appendix.json"
    artifact_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print("RUBRIC APPENDIX STRUCTURE VALIDATION")
    print(f"{'='*60}")

    # Display the full appendix
    for ra in report.rubric_appendix:
        print(f"\n  [{ra.dimension}] score={ra.score:.2f}")
        if ra.reasoning:
            print(f"    Reasoning: {ra.reasoning}")
        if ra.strengths:
            print(f"    Strengths:")
            for s in ra.strengths:
                print(f"      + {s}")
        if ra.gaps:
            print(f"    Gaps:")
            for g in ra.gaps:
                print(f"      - {g}")
        if ra.evidence:
            print(f"    Evidence:")
            for e in ra.evidence:
                print(f"      • {e}")

    # Structural checks
    expected_dimensions = {"completeness", "accuracy", "style_compliance", "readability", "grounding"}
    appendix_dimensions = {ra.dimension for ra in report.rubric_appendix}

    # Build score map from rubric appendix
    appendix_scores = {ra.dimension: ra.score for ra in report.rubric_appendix}
    report_scores = {
        "completeness": report.scores.completeness,
        "accuracy": report.scores.accuracy,
        "style_compliance": report.scores.style_compliance,
        "readability": report.scores.readability,
        "grounding": report.scores.grounding,
    }

    checks = {
        "rubric_appendix is not empty": len(report.rubric_appendix) > 0,
        "has all 5 dimensions": expected_dimensions.issubset(appendix_dimensions),
        "all entries have reasoning": all(ra.reasoning for ra in report.rubric_appendix),
        "all entries have evidence": all(len(ra.evidence) > 0 for ra in report.rubric_appendix),
        "all entries have strengths": all(len(ra.strengths) > 0 for ra in report.rubric_appendix),
    }

    # Check score consistency (appendix scores match report scores)
    score_mismatches = []
    for dim in expected_dimensions:
        if dim in appendix_scores and dim in report_scores:
            if abs(appendix_scores[dim] - report_scores[dim]) > 0.01:
                score_mismatches.append(
                    f"{dim}: appendix={appendix_scores[dim]:.2f} vs report={report_scores[dim]:.2f}"
                )
    checks["scores match between appendix and report"] = len(score_mismatches) == 0

    print(f"\n{'─'*60}")
    print("Validation checks:")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    if score_mismatches:
        print("\nScore mismatches:")
        for m in score_mismatches:
            print(f"  ⚠ {m}")

    print(f"\nArtifact: {artifact_path}")

    # Assertions — rubric appendix should exist and have all dimensions
    assert len(report.rubric_appendix) > 0, (
        "Rubric appendix should not be empty — the evaluate prompt requests it"
    )
    assert expected_dimensions.issubset(appendix_dimensions), (
        f"Rubric appendix should cover all 5 dimensions. "
        f"Missing: {expected_dimensions - appendix_dimensions}"
    )
    # All entries should have reasoning
    for ra in report.rubric_appendix:
        assert ra.reasoning, f"Rubric entry for '{ra.dimension}' should have reasoning"
        assert len(ra.evidence) > 0, f"Rubric entry for '{ra.dimension}' should have evidence"
