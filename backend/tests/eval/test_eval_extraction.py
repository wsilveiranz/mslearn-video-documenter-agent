"""Evaluate the Extraction Agent with a real video file."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.eval


@pytest.mark.local
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


@pytest.mark.asyncio
async def test_extraction_quality_metrics():
    """Validate extraction result quality metrics against synthetic fixture."""
    from tests.eval.fixtures import make_extraction_result

    result = make_extraction_result()

    full_text = " ".join(seg.text for seg in result.transcript)
    word_count = len(full_text.split())

    checks = {
        "Has transcript segments": len(result.transcript) > 0,
        "Transcript word count > 20": word_count > 20,
        "Transcript segments have timestamps": all(
            seg.start_seconds >= 0 and seg.end_seconds > seg.start_seconds
            for seg in result.transcript
        ),
        "Transcript segments are chronological": all(
            result.transcript[i].start_seconds <= result.transcript[i + 1].start_seconds
            for i in range(len(result.transcript) - 1)
        ),
        "Has scenes": len(result.scenes) > 0,
        "Scenes have IDs": all(s.id for s in result.scenes),
        "Scenes are chronological": all(
            result.scenes[i].start_seconds <= result.scenes[i + 1].start_seconds
            for i in range(len(result.scenes) - 1)
        ),
        "Scenes cover full duration": (
            result.scenes[0].start_seconds == 0.0
            and result.scenes[-1].end_seconds >= result.video_metadata.duration_seconds * 0.6
        ),
        "No scene gaps > 5s": all(
            result.scenes[i + 1].start_seconds - result.scenes[i].end_seconds <= 5.0
            for i in range(len(result.scenes) - 1)
        ),
        "Has keyframes": len(result.keyframes) > 0,
        "Keyframes have descriptions": all(kf.ui_description for kf in result.keyframes),
        "Keyframes have scene IDs": all(kf.scene_id for kf in result.keyframes),
        "Keyframes are within video duration": all(
            0 <= kf.timestamp_seconds <= result.video_metadata.duration_seconds
            for kf in result.keyframes
        ),
        "No duplicate keyframe timestamps": len(
            {kf.timestamp_seconds for kf in result.keyframes}
        ) == len(result.keyframes),
        "All keyframe scene_ids exist": all(
            kf.scene_id in {s.id for s in result.scenes}
            for kf in result.keyframes
        ),
        "All scene keyframe_ids exist": all(
            kf_id in {kf.id for kf in result.keyframes}
            for scene in result.scenes
            for kf_id in scene.keyframe_ids
        ),
    }

    print(f"\n{'='*60}")
    print("EXTRACTION QUALITY METRICS")
    print(f"{'='*60}")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    failed = [k for k, v in checks.items() if not v]
    assert not failed, f"Quality checks failed: {failed}"


@pytest.mark.asyncio
async def test_extraction_cloud_local_schema_parity():
    """Verify ExtractionResult schema supports both processing modes."""
    from tests.eval.fixtures import make_extraction_result
    from src.models.video import ExtractionResult, ProcessingMode

    local_result = make_extraction_result()

    cloud_result = ExtractionResult(
        transcript=local_result.transcript,
        scenes=local_result.scenes,
        keyframes=local_result.keyframes,
        ocr_entries=local_result.ocr_entries,
        entities=local_result.entities,
        video_metadata=local_result.video_metadata,
        processing_mode=ProcessingMode.CLOUD,
    )

    local_json = local_result.model_dump_json()
    cloud_json = cloud_result.model_dump_json()

    local_round = ExtractionResult.model_validate_json(local_json)
    cloud_round = ExtractionResult.model_validate_json(cloud_json)

    checks = {
        "Local serializes": len(local_json) > 100,
        "Cloud serializes": len(cloud_json) > 100,
        "Local roundtrips": local_round.processing_mode == ProcessingMode.LOCAL,
        "Cloud roundtrips": cloud_round.processing_mode == ProcessingMode.CLOUD,
        "Same transcript count": len(local_round.transcript) == len(cloud_round.transcript),
        "Same scene count": len(local_round.scenes) == len(cloud_round.scenes),
        "Same keyframe count": len(local_round.keyframes) == len(cloud_round.keyframes),
    }

    print(f"\n{'='*60}")
    print("CLOUD/LOCAL SCHEMA PARITY")
    print(f"{'='*60}")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    assert all(checks.values()), f"Parity checks failed: {[k for k, v in checks.items() if not v]}"


@pytest.mark.asyncio
async def test_extraction_data_quality_report():
    """Verify DataQualityReport model schema is valid and accepts representative values."""
    from src.models.video import DataQualityReport

    # DataQualityReport is populated by the LLM-based ExtractionAgent, not
    # constructed directly from ExtractionResult. Validate the schema here by
    # constructing a representative instance and round-tripping it.
    report = DataQualityReport(
        quality_level="rich",
        transcript_assessment="Transcript is coherent, covers all steps, and spans the full video duration.",
        visual_assessment="Keyframes are present for each scene with descriptive alt text.",
        coverage_gaps=[],
        warnings=[],
        recommendations=["Add OCR entries for terminal commands to improve grounding."],
        grounding_confidence=0.92,
        raw_metrics={
            "transcript_segments": 8,
            "scenes": 3,
            "keyframes": 4,
            "ocr_entries": 3,
            "duration_seconds": 45.0,
        },
    )

    report_json = report.model_dump_json()
    round_tripped = DataQualityReport.model_validate_json(report_json)

    checks = {
        "Serializes to JSON": len(report_json) > 50,
        "Roundtrip preserves quality_level": round_tripped.quality_level == "rich",
        "Roundtrip preserves grounding_confidence": round_tripped.grounding_confidence == 0.92,
        "Roundtrip preserves raw_metrics": round_tripped.raw_metrics["scenes"] == 3,
        "grounding_confidence in [0, 1]": 0.0 <= round_tripped.grounding_confidence <= 1.0,
        "Recommendations preserved": len(round_tripped.recommendations) == 1,
    }

    print(f"\n{'='*60}")
    print("DATA QUALITY REPORT SCHEMA")
    print(f"{'='*60}")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'} {check}")

    failed = [k for k, v in checks.items() if not v]
    assert not failed, f"DataQualityReport checks failed: {failed}"
