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
