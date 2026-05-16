"""Full end-to-end pipeline evaluation."""

from __future__ import annotations

import json

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


@pytest.mark.parametrize("doc_type", [pytest.param("overview"), pytest.param("concept"), pytest.param("how-to")])
@pytest.mark.asyncio
async def test_pipeline_multi_doctype(video_path, eval_output, foundry_client, doc_type):
    """Run full pipeline for each priority doc type and evaluate output."""
    from src.agents.orchestrator import PipelineInput, run_pipeline
    from src.models.document import DocType
    from src.models.video import ProcessingMode
    from tests.eval.graders import run_all_style_checks

    doc_type_enum = DocType(doc_type)

    request = PipelineInput(
        video_source=str(video_path),
        doc_type=doc_type_enum,
        processing_mode=ProcessingMode.LOCAL,
    )

    workflow_result = await run_pipeline.run(request)
    outputs = workflow_result.get_outputs()
    assert len(outputs) > 0, f"Pipeline should produce output for {doc_type}"
    result = outputs[0]

    # Save artifacts
    doc_type_name = doc_type.replace("-", "_")
    (eval_output / f"pipeline_{doc_type_name}_document.md").write_text(
        result.document.markdown_content, encoding="utf-8"
    )
    (eval_output / f"pipeline_{doc_type_name}_document.json").write_text(
        result.document.model_dump_json(indent=2), encoding="utf-8"
    )
    (eval_output / f"pipeline_{doc_type_name}_evaluation.json").write_text(
        result.evaluation.model_dump_json(indent=2), encoding="utf-8"
    )

    # Rule-based grading
    style_report = run_all_style_checks(result.document.markdown_content, doc_type)

    print(f"\n{'='*60}")
    print(f"PIPELINE EVALUATION — {doc_type.upper()}")
    print(f"{'='*60}")
    print(f"Word count:     {result.document.word_count}")
    print(f"Quality score:  {result.evaluation.scores.overall:.2f}")
    print(f"Passed:         {'YES' if result.evaluation.passed else 'NO'}")
    print(f"Style errors:   {len(style_report.errors)}")
    print(f"Style warnings: {len(style_report.warnings)}")
    print(f"Style:          {style_report.summary()}")

    assert result.document.word_count > 100, "Should have substantial content"
    assert result.evaluation.scores.overall > 0, "Scores should not be zero"


@pytest.mark.asyncio
async def test_pipeline_with_corpus(corpus_videos, eval_output, foundry_client):
    """Run pipeline for each video in the corpus against its configured doc types."""
    from src.agents.orchestrator import PipelineInput, run_pipeline
    from src.models.document import DocType
    from src.models.video import ProcessingMode
    from tests.eval.graders import run_all_style_checks

    results_summary = []

    for video_path, video_config in corpus_videos:
        for doc_type_str in video_config.get("doc_types", ["how-to"]):
            doc_type = DocType(doc_type_str)
            video_id = video_config["id"]

            print(f"\n--- {video_id} × {doc_type.value} ---")

            request = PipelineInput(
                video_source=str(video_path),
                doc_type=doc_type,
                processing_mode=ProcessingMode.LOCAL,
            )

            try:
                workflow_result = await run_pipeline.run(request)
                outputs = workflow_result.get_outputs()
                if not outputs:
                    print("  SKIP: No output produced")
                    continue

                result = outputs[0]
                style_report = run_all_style_checks(result.document.markdown_content, doc_type.value)

                entry = {
                    "video_id": video_id,
                    "doc_type": doc_type.value,
                    "word_count": result.document.word_count,
                    "overall_score": result.evaluation.scores.overall,
                    "passed": result.evaluation.passed,
                    "style_errors": len(style_report.errors),
                    "style_warnings": len(style_report.warnings),
                }
                results_summary.append(entry)

                # Save per-run artifact
                artifact_name = f"corpus_{video_id}_{doc_type.value.replace('-', '_')}"
                (eval_output / f"{artifact_name}.md").write_text(
                    result.document.markdown_content, encoding="utf-8"
                )

                print(
                    f"  Score: {result.evaluation.scores.overall:.2f} | "
                    f"Passed: {result.evaluation.passed} | "
                    f"Style: {len(style_report.errors)}e/{len(style_report.warnings)}w"
                )

            except Exception as e:
                print(f"  ERROR: {e}")
                results_summary.append({
                    "video_id": video_id,
                    "doc_type": doc_type.value,
                    "error": str(e),
                })

    # Save summary
    summary_path = eval_output / "corpus_eval_summary.json"
    summary_path.write_text(json.dumps(results_summary, indent=2), encoding="utf-8")
    print(f"\nSummary saved to: {summary_path}")

    assert len(results_summary) > 0, "Should have evaluated at least one video"


@pytest.mark.asyncio
async def test_pipeline_with_llm_judge(video_path, eval_output, foundry_client):
    """Run pipeline and evaluate output with LLM-as-judge on all dimensions."""
    from src.agents.orchestrator import PipelineInput, run_pipeline
    from src.models.document import DocType
    from src.models.video import ProcessingMode
    from src.services.llm_judge import LLMJudge

    request = PipelineInput(
        video_source=str(video_path),
        doc_type=DocType.HOWTO,
        processing_mode=ProcessingMode.LOCAL,
    )

    workflow_result = await run_pipeline.run(request)
    outputs = workflow_result.get_outputs()
    assert len(outputs) > 0
    result = outputs[0]

    # Run LLM-as-judge on all dimensions
    judge = LLMJudge(foundry_client)
    judge_results = await judge.evaluate_all(result.document.markdown_content)

    print(f"\n{'='*60}")
    print("LLM-AS-JUDGE EVALUATION")
    print(f"{'='*60}")
    for dim, jr in judge_results.items():
        print(f"  {dim}: {jr.score:.2f}")
        if jr.sub_scores:
            for sub, score in jr.sub_scores.items():
                print(f"    {sub}: {score:.2f}")

    # Save judge results
    judge_path = eval_output / "llm_judge_results.json"
    judge_data = {
        dim: {"score": jr.score, "reasoning": jr.reasoning, "sub_scores": jr.sub_scores}
        for dim, jr in judge_results.items()
    }
    judge_path.write_text(json.dumps(judge_data, indent=2), encoding="utf-8")

    for dim, jr in judge_results.items():
        print(f"  {'PASS' if jr.score >= 0.5 else 'WARN'} {dim}: {jr.score:.2f}")
