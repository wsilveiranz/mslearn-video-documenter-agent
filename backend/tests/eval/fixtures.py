# ruff: noqa: E501
"""Synthetic test fixtures for standalone agent evaluation."""

from __future__ import annotations

from src.models.document import (
    DocType,
    DocumentOutline,
    DocumentSection,
    Frontmatter,
    GeneratedDocument,
)
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


def make_extraction_result() -> ExtractionResult:
    """Create a realistic ExtractionResult for testing LLM agents."""
    metadata = VideoMetadata(
        video_id="eval-test-001",
        source_path="test_videos/CloneToStandard-ShortDemo.mp4",
        source_type=VideoSourceType.LOCAL_FILE,
        duration_seconds=45.0,
        resolution_width=1920,
        resolution_height=1080,
        fps=30.0,
        file_size_bytes=5_000_000,
    )

    transcript = [
        TranscriptSegment(
            text="Welcome to this tutorial on cloning a repository in Azure DevOps.",
            start_seconds=0.0,
            end_seconds=4.0,
        ),
        TranscriptSegment(
            text="First, navigate to the Azure DevOps portal and select your project.",
            start_seconds=4.5,
            end_seconds=8.0,
        ),
        TranscriptSegment(
            text="Click on the Repos section in the left navigation.",
            start_seconds=8.5,
            end_seconds=11.0,
        ),
        TranscriptSegment(
            text="Now click the Clone button in the top right corner.",
            start_seconds=11.5,
            end_seconds=14.0,
        ),
        TranscriptSegment(
            text="Copy the HTTPS clone URL that appears.",
            start_seconds=14.5,
            end_seconds=17.0,
        ),
        TranscriptSegment(
            text="Open your terminal and run git clone followed by the URL.",
            start_seconds=17.5,
            end_seconds=21.0,
        ),
        TranscriptSegment(
            text="The repository is now cloned to your local machine.",
            start_seconds=21.5,
            end_seconds=24.0,
        ),
        TranscriptSegment(
            text="You can verify by navigating into the directory and running git status.",
            start_seconds=24.5,
            end_seconds=28.0,
        ),
    ]

    scenes = [
        Scene(
            id="scene_000",
            start_seconds=0.0,
            end_seconds=8.0,
            keyframe_ids=["kf_000"],
            description="Azure DevOps portal overview",
        ),
        Scene(
            id="scene_001",
            start_seconds=8.0,
            end_seconds=17.0,
            keyframe_ids=["kf_001", "kf_002"],
            description="Navigate to Repos and clone",
        ),
        Scene(
            id="scene_002",
            start_seconds=17.0,
            end_seconds=28.0,
            keyframe_ids=["kf_003"],
            description="Terminal clone and verification",
        ),
    ]

    keyframes = [
        Keyframe(
            id="kf_000",
            timestamp_seconds=4.0,
            image_path="tests/eval/output/frames/frame_001.png",
            ui_description=(
                "Azure DevOps project page showing the main dashboard with "
                "Repos, Pipelines, and Boards in the left navigation."
            ),
            scene_id="scene_000",
        ),
        Keyframe(
            id="kf_001",
            timestamp_seconds=10.0,
            image_path="tests/eval/output/frames/frame_002.png",
            ui_description=(
                "Azure DevOps Repos page with file listing and a Clone button "
                "visible in the top-right toolbar."
            ),
            scene_id="scene_001",
        ),
        Keyframe(
            id="kf_002",
            timestamp_seconds=14.0,
            image_path="tests/eval/output/frames/frame_003.png",
            ui_description="Clone dialog box showing HTTPS URL with a copy button highlighted.",
            scene_id="scene_001",
        ),
        Keyframe(
            id="kf_003",
            timestamp_seconds=22.0,
            image_path="tests/eval/output/frames/frame_004.png",
            ui_description=(
                "Terminal window showing successful git clone output with "
                "repository files listed."
            ),
            scene_id="scene_002",
        ),
    ]

    ocr_entries = [
        OCREntry(text="Clone to your computer", timestamp_seconds=11.0),
        OCREntry(text="https://dev.azure.com/org/project/_git/repo", timestamp_seconds=14.0),
        OCREntry(text="git clone https://dev.azure.com/org/project/_git/repo", timestamp_seconds=19.0),
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


def make_document_outline() -> DocumentOutline:
    """Create a realistic DocumentOutline for testing Writer/Editor agents."""
    return DocumentOutline(
        doc_type=DocType.TUTORIAL,
        frontmatter=Frontmatter(
            title="Tutorial: Clone a repository in Azure DevOps",
            description=(
                "Learn how to clone an Azure DevOps Git repository to your "
                "local machine using the portal and command line."
            ),
        ),
        sections=[
            DocumentSection(
                heading="Tutorial: Clone a repository in Azure DevOps",
                level=1,
                content_hint="Introduction explaining what the tutorial covers",
            ),
            DocumentSection(
                heading="Prerequisites",
                level=2,
                content_hint="List prerequisites: Azure DevOps account, Git installed",
            ),
            DocumentSection(
                heading="Navigate to Azure DevOps Repos",
                level=2,
                content_hint="Steps to find the Repos section",
                source_scenes=["scene_000", "scene_001"],
            ),
            DocumentSection(
                heading="Clone the repository",
                level=2,
                content_hint="Steps to clone using git clone",
                source_scenes=["scene_001", "scene_002"],
                steps=["Click Clone button", "Copy HTTPS URL", "Run git clone in terminal"],
            ),
            DocumentSection(
                heading="Verify the clone",
                level=2,
                content_hint="Verify with git status",
                source_scenes=["scene_002"],
            ),
            DocumentSection(
                heading="Clean up resources",
                level=2,
                content_hint="Optional cleanup steps",
            ),
            DocumentSection(
                heading="Next steps",
                level=2,
                content_hint="Links to related tutorials",
            ),
        ],
        screenshots=[],
        estimated_word_count=500,
    )


def make_generated_document() -> GeneratedDocument:
    """Create a realistic GeneratedDocument for testing Editor/Evaluate agents.

    NOTE: This document intentionally contains MS Learn style issues for the
    Editor to catch:
    - "Tutorial" capitalized mid-sentence in H1 intro paragraph
    - "Repository" capitalized incorrectly in several places
    - "Your" capitalized incorrectly
    - "repos" not capitalized consistently
    - "Branch" and "Directory" incorrectly capitalized
    - Step numbering restarts (should be continuous 1.)
    - Missing period after some sentences
    """
    markdown = '''---
title: "Tutorial: Clone a repository in Azure DevOps"
description: "Learn how to clone an Azure DevOps Git repository to your local machine using the portal and command line."
author: video-documenter
ms.author: video-documenter
ms.date: 05/09/2026
ms.topic: tutorial
ms.service: azure-devops
ms.custom: ai-assisted
# Customer intent: As a developer, I want to clone a repository so that I can work with the code locally.
---

# Tutorial: Clone a repository in Azure DevOps

In this Tutorial, you learn how to clone a Git repository from Azure DevOps to your local machine.

> [!div class="checklist"]
> * Navigate to Azure DevOps Repos
> * Clone the Repository using HTTPS
> * Verify the clone on your local machine

## Prerequisites

- An Azure DevOps organization and project with a Git Repository
- [Git](https://git-scm.com/) installed on your local machine
- Access to the Repository you want to clone

## Navigate to Azure DevOps Repos

1. Sign in to [Azure DevOps](https://dev.azure.com).
1. Select Your project from the dashboard.
1. In the left navigation, select **repos**.

:::image type="content" source="./media/step-01.png" alt-text="Azure DevOps project page showing the Repos option in the left navigation":::

## Clone the Repository

1. On the Repos page, click the **Clone** button in the top-right toolbar.
1. In the Clone dialog, copy the **HTTPS** URL.
1. Open your terminal and navigate to the directory where you want to clone the repository.
1. Run the following command:

```bash
git clone https://dev.azure.com/org/project/_git/repo
```

:::image type="content" source="./media/step-02.png" alt-text="Clone dialog showing HTTPS URL with copy button":::

## Verify the Clone

1. Navigate into the cloned directory:

```bash
cd repo
```

2. Run `git status` to verify:

```bash
git status
```

You should see a message indicating you\'re on the main Branch.

## Clean Up Resources

If you no longer need the local clone, delete the Directory:

```bash
rm -rf repo
```

## Next steps

> [!div class="nextstepaction"]
> [Create a branch](create-branch.md)
'''
    outline = make_document_outline()
    return GeneratedDocument(
        document_id="eval-doc-001",
        doc_type=DocType.TUTORIAL,
        outline=outline,
        markdown_content=markdown,
        media_files=[],
        word_count=len(markdown.split()),
        revision_number=1,
    )
