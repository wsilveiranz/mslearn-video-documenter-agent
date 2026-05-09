"""Full end-to-end pipeline evaluation."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.integration]


@pytest.mark.asyncio
async def test_full_pipeline(video_path, eval_output, foundry_client):
    """Run the complete pipeline end-to-end with a real video."""
    from src.agents.orchestrator import PipelineInput, run_pipeline
    from src.models.document import DocType
    from src.models.video import ProcessingMode

    request = PipelineInput(
        video_source=str(video_path),
        doc_type=DocType.TUTORIAL,
        processing_mode=ProcessingMode.LOCAL,
    )

    # run_pipeline is a @workflow — call .run() which returns WorkflowRunResult
    workflow_result = await run_pipeline.run(request)
    outputs = workflow_result.get_outputs()
    assert len(outputs) > 0, "Pipeline should produce at least one output"
    result = outputs[0]

    # Save all artifacts
    (eval_output / "pipeline_document.md").write_text(result.document.markdown_content, encoding="utf-8")
    (eval_output / "pipeline_document.json").write_text(result.document.model_dump_json(indent=2), encoding="utf-8")
    (eval_output / "pipeline_evaluation.json").write_text(
        result.evaluation.model_dump_json(indent=2), encoding="utf-8"
    )

    print(f"\n{'='*60}")
    print("FULL PIPELINE EVALUATION")
    print(f"{'='*60}")
    print(f"Document ID:   {result.document.document_id}")
    print(f"Word count:    {result.document.word_count}")
    print(f"Revisions:     {result.document.revision_number}")
    print(f"Quality score: {result.evaluation.scores.overall:.2f}")
    print(f"Passed:        {'YES' if result.evaluation.passed else 'NO'}")
    print(f"\nArtifacts saved to: {eval_output}")

    assert result.document.word_count > 100
    assert result.evaluation.scores.overall > 0
