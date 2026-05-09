"""Evaluate the Extraction Agent with a real video file."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.local]


@pytest.mark.asyncio
async def test_extraction_agent(video_path, eval_output):
    """Test extraction pipeline with a real video."""
    from src.agents.extraction import ExtractionAgent
    from src.agents.ingestion import IngestionAgent
    from src.models.video import IngestionResult, ProcessingMode

    # Check for cached ingestion result
    ingestion_path = eval_output / "ingestion_result.json"
    if ingestion_path.exists():
        ingestion_result = IngestionResult.model_validate_json(ingestion_path.read_text())
        metadata = ingestion_result.metadata
        # Update source path to actual video location
        metadata.source_path = str(video_path)
    else:
        ingestion_agent = IngestionAgent()
        ingestion_result = await ingestion_agent.process(str(video_path), ProcessingMode.LOCAL)
        metadata = ingestion_result.metadata

    # Run extraction (no foundry client — skip vision analysis for this test)
    agent = ExtractionAgent(foundry_client=None)
    result = await agent.process(metadata, ProcessingMode.LOCAL)

    # Save artifact
    artifact_path = eval_output / "extraction_result.json"
    artifact_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    # Quality checks
    print(f"\n{'='*60}")
    print("EXTRACTION AGENT EVALUATION")
    print(f"{'='*60}")
    print(f"Transcript segments: {len(result.transcript)}")
    print(f"Scenes detected:     {len(result.scenes)}")
    print(f"Keyframes extracted: {len(result.keyframes)}")
    print(f"OCR entries:         {len(result.ocr_entries)}")

    if result.transcript:
        full_text = " ".join(seg.text for seg in result.transcript)
        print(f"Transcript length:   {len(full_text)} chars")
        print(f"Transcript preview:  {full_text[:200]}...")

    if result.scenes:
        for scene in result.scenes:
            print(
                f"  Scene {scene.id}: {scene.start_seconds:.1f}s - "
                f"{scene.end_seconds:.1f}s ({len(scene.keyframe_ids)} keyframes)"
            )

    assert len(result.transcript) > 0, "Should have transcribed some speech"
    assert len(result.scenes) > 0, "Should have detected at least one scene"
    assert len(result.keyframes) > 0, "Should have extracted at least one keyframe"

    print(f"Artifact:            {artifact_path}")
    print("RESULT:              PASS")
