"""Unit tests for StructureAgent with mocked FoundryChatClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.structure import StructureAgent
from src.models.document import DocType
from src.models.video import ExtractionResult, ProcessingMode, TranscriptSegment, VideoMetadata, VideoSourceType


def _make_extraction() -> ExtractionResult:
    return ExtractionResult(
        transcript=[
            TranscriptSegment(text="Welcome to the tutorial", start_seconds=0.0, end_seconds=3.0),
            TranscriptSegment(text="First open the portal", start_seconds=3.0, end_seconds=6.0),
        ],
        scenes=[],
        keyframes=[],
        ocr_entries=[],
        entities=[],
        video_metadata=VideoMetadata(
            video_id="test123",
            source_path="/fake/video.mp4",
            source_type=VideoSourceType.LOCAL_FILE,
            duration_seconds=60.0,
            resolution_width=1920,
            resolution_height=1080,
            fps=30.0,
            file_size_bytes=1024,
        ),
        processing_mode=ProcessingMode.LOCAL,
    )


def _make_llm_response(title: str = "Tutorial: Deploy a web app") -> str:
    data = {
        "title": title,
        "description": "Learn how to deploy a web application to Azure App Service step by step.",
        "ms_service": "app-service",
        "sections": [
            {"heading": "Prerequisites", "notes": "What you need", "scene_ids": []},
            {"heading": "Create the resource", "notes": "Step-by-step", "scene_ids": []},
        ],
    }
    return f"```json\n{json.dumps(data)}\n```"


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def agent(mock_client):
    with patch.object(StructureAgent, "_load_system_prompt"):
        a = StructureAgent(mock_client)
        a._system_prompt = "You are a test prompt."
        return a


class TestStructureAgent:
    async def test_process_returns_valid_outline(self, agent):
        """Test that process returns a DocumentOutline with correct sections."""
        llm_response = _make_llm_response()

        with patch.object(agent, "_run_agent", new_callable=AsyncMock, return_value=llm_response):
            result = await agent.process(_make_extraction(), DocType.TUTORIAL)

        assert result.doc_type == DocType.TUTORIAL
        assert result.frontmatter.title == "Tutorial: Deploy a web app"
        assert len(result.sections) == 2
        assert result.sections[0].heading == "Prerequisites"

    async def test_process_falls_back_on_bad_json(self, agent):
        """Test fallback to minimal outline when LLM returns invalid JSON."""
        with patch.object(agent, "_run_agent", new_callable=AsyncMock, return_value="not json at all"):
            result = await agent.process(_make_extraction(), DocType.QUICKSTART)

        assert result.doc_type == DocType.QUICKSTART
        assert len(result.sections) >= 2  # Minimal fallback has sections

    async def test_process_handles_empty_response(self, agent):
        """Test fallback when LLM returns empty response."""
        with patch.object(agent, "_run_agent", new_callable=AsyncMock, return_value=""):
            result = await agent.process(_make_extraction(), DocType.HOWTO)

        assert result.doc_type == DocType.HOWTO
        assert len(result.sections) >= 2
