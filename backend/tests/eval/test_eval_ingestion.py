"""Evaluate the Ingestion Agent with a real video file."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.local]


@pytest.mark.asyncio
async def test_ingestion_agent(video_path, eval_output):
    """Test ingestion with a real video file."""
    from src.agents.ingestion import IngestionAgent
    from src.models.video import ProcessingMode

    agent = IngestionAgent()
    result = await agent.process(str(video_path), ProcessingMode.LOCAL)

    # Save artifact
    artifact_path = eval_output / "ingestion_result.json"
    artifact_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    # Quality checks
    assert result.video_id, "video_id should not be empty"
    assert result.metadata.duration_seconds > 0, "duration should be positive"
    assert result.metadata.resolution_width > 0, "resolution width should be positive"
    assert result.metadata.resolution_height > 0, "resolution height should be positive"
    assert result.metadata.fps > 0, "fps should be positive"
    assert result.metadata.file_size_bytes > 0, "file size should be positive"

    print(f"\n{'='*60}")
    print("INGESTION AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Video ID:    {result.video_id}")
    print(f"Duration:    {result.metadata.duration_seconds:.1f}s")
    print(f"Resolution:  {result.metadata.resolution_width}x{result.metadata.resolution_height}")
    print(f"FPS:         {result.metadata.fps}")
    print(f"File size:   {result.metadata.file_size_bytes / 1024 / 1024:.2f} MB")
    print(f"Artifact:    {artifact_path}")
    print("RESULT:      PASS")
