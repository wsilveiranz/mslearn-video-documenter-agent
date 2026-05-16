"""Shared fixtures and CLI options for agent evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--video",
        default="test_videos/CloneToStandard-ShortDemo.mp4",
        help="Path to test video file",
    )
    parser.addoption(
        "--eval-output",
        default="tests/eval/output",
        help="Directory for evaluation artifacts",
    )
    parser.addoption(
        "--reference-url",
        default="https://learn.microsoft.com/en-us/azure/logic-apps/clone-consumption-logic-app-to-standard-workflow",
        help="URL of the published MS Learn article to use as evaluation reference",
    )
    parser.addoption(
        "--eval-corpus",
        default=None,
        help="Path to evaluation video corpus directory (overrides EVAL_VIDEO_CORPUS_PATH env var)",
    )


@pytest.fixture
def video_path(request):
    """Path to the test video file."""
    path = Path(request.config.getoption("--video"))
    if not path.is_absolute():
        path = Path(__file__).parent.parent.parent.parent / path  # relative to repo root
    if not path.exists():
        pytest.skip(f"Test video not found: {path}")
    return path


@pytest.fixture
def eval_output(request):
    """Output directory for evaluation artifacts."""
    path = Path(request.config.getoption("--eval-output"))
    if not path.is_absolute():
        path = Path(__file__).parent.parent.parent / path
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def foundry_client():
    """Create a real FoundryChatClient for LLM agent testing."""
    try:
        from src.agents.orchestrator import create_foundry_client

        return create_foundry_client()
    except Exception as e:
        pytest.skip(f"Azure AI Foundry not available: {e}")


@pytest.fixture
def reference_url(request):
    """URL of the published MS Learn article for reference-based evaluation."""
    return request.config.getoption("--reference-url")


@pytest.fixture
def corpus_path(request):
    """Path to the evaluation video corpus directory.
    
    Resolution order:
    1. --eval-corpus CLI option
    2. EVAL_VIDEO_CORPUS_PATH environment variable
    3. Default: backend/tests/eval/corpus/
    """
    import os
    
    cli_path = request.config.getoption("--eval-corpus")
    if cli_path:
        path = Path(cli_path)
    else:
        env_path = os.environ.get("EVAL_VIDEO_CORPUS_PATH")
        if env_path:
            path = Path(env_path)
        else:
            path = Path(__file__).parent / "corpus"
    
    if not path.exists():
        pytest.skip(f"Corpus directory not found: {path}")
    return path


@pytest.fixture
def corpus_manifest(corpus_path):
    """Load the corpus manifest file."""
    import json
    
    manifest_path = corpus_path / "manifest.json"
    if not manifest_path.exists():
        pytest.skip(f"Corpus manifest not found: {manifest_path}")
    
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def corpus_videos(corpus_path, corpus_manifest):
    """Return list of (video_path, video_config) for available videos."""
    videos = []
    for video_config in corpus_manifest.get("videos", []):
        video_file = corpus_path / video_config["filename"]
        if video_file.exists():
            videos.append((video_file, video_config))
    
    if not videos:
        pytest.skip("No video files found in corpus directory")
    return videos
