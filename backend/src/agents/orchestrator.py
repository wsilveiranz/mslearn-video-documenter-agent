"""Pipeline Orchestrator — coordinates the 6-agent documentation pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from agent_framework import workflow
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel, Field

from src.config import get_settings
from src.models.document import DocType, DocumentMetadata
from src.models.video import ExtractionResult, ProcessingMode
from src.services.copilot_client import create_copilot_client

from .editor import EditorAgent
from .evaluate import EvaluateAgent
from .extraction import ExtractionAgent
from .ingestion import IngestionAgent
from .structure import StructureAgent
from .writer import WriterAgent

if TYPE_CHECKING:
    from src.models.document import GeneratedDocument
    from src.models.evaluation import EvaluationReport

logger = structlog.get_logger()

MAX_REVISION_ITERATIONS = 3


class PipelineInput(BaseModel):
    """Input parameters for the documentation pipeline."""

    video_source: str = Field(description="Path or URL to the video file")
    doc_type: DocType = Field(description="Which MS Learn document type to generate")
    processing_mode: ProcessingMode | None = Field(
        default=None, description="Cloud or local. Defaults to config setting"
    )
    supplementary_context: str = Field(
        default="", description="Additional context (README, API specs, etc.)"
    )
    metadata: DocumentMetadata | None = Field(
        default=None, description="User-provided frontmatter metadata"
    )


def create_foundry_client() -> FoundryChatClient:
    """Create a FoundryChatClient using DefaultAzureCredential."""
    settings = get_settings()
    return FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model,
        credential=DefaultAzureCredential(),
    )


def create_llm_client(processing_mode: ProcessingMode | None = None):
    """Create the appropriate LLM client based on processing mode and config.

    Rules:
    - ``processing_mode="cloud"`` → always Azure AI Foundry, ignoring proxy config.
    - ``processing_mode="local"`` and ``copilot_proxy_url`` configured → Copilot LM Proxy.
    - No mode supplied → falls back to ``settings.use_copilot_proxy`` (existing behaviour).
    """
    settings = get_settings()

    if processing_mode == ProcessingMode.CLOUD:
        logger.info("pipeline.using_foundry", reason="processing_mode=cloud")
        return create_foundry_client()

    if processing_mode == ProcessingMode.LOCAL and settings.copilot_proxy_url:
        logger.info("pipeline.using_copilot_proxy", proxy_url=settings.copilot_proxy_url)
        return create_copilot_client(
            settings.copilot_proxy_url,
            model=settings.copilot_proxy_model,
            secret=settings.copilot_proxy_secret,
        )

    if processing_mode == ProcessingMode.LOCAL and not settings.copilot_proxy_url:
        logger.warning(
            "pipeline.local_mode_no_proxy",
            reason="processing_mode=local but copilot_proxy_url is not configured; falling back to Foundry",
        )

    # Default: honour global settings flag (no explicit mode supplied)
    if settings.use_copilot_proxy:
        logger.info("pipeline.using_copilot_proxy", proxy_url=settings.copilot_proxy_url)
        return create_copilot_client(
            settings.copilot_proxy_url,
            model=settings.copilot_proxy_model,
            secret=settings.copilot_proxy_secret,
        )
    return create_foundry_client()


class PipelineResult:
    """Result of a full pipeline run."""

    def __init__(
        self,
        document: GeneratedDocument,
        evaluation: EvaluationReport,
        extraction: ExtractionResult,
    ) -> None:
        self.document = document
        self.evaluation = evaluation
        self.extraction = extraction


@workflow
async def run_pipeline(request: PipelineInput) -> PipelineResult:
    """Run the full video-to-documentation pipeline.

    Pipeline: Ingestion → Extraction → Structure → Writer → Editor → Evaluate

    Args:
        request: Pipeline input with video source, doc type, mode, and context.

    Returns:
        PipelineResult with the generated document, evaluation, and extraction data.
    """
    settings = get_settings()
    mode = request.processing_mode or ProcessingMode(settings.processing_mode)

    logger.info("pipeline.start", source=request.video_source, doc_type=request.doc_type, mode=mode)

    # Create shared LLM client — pass resolved mode so cloud requests always use Foundry
    client = create_llm_client(mode)

    # Stage 1: Ingestion
    logger.info("pipeline.stage", stage="ingestion")
    ingestion_agent = IngestionAgent()
    ingestion_result = await ingestion_agent.process(request.video_source, mode)

    # Stage 2: Extraction
    logger.info("pipeline.stage", stage="extraction")
    extraction_agent = ExtractionAgent(foundry_client=client)
    extraction_result = await extraction_agent.process(ingestion_result.metadata, mode)

    # Validate extraction produced meaningful data
    if not extraction_result.transcript and not extraction_result.scenes and not extraction_result.keyframes:
        msg = (
            "Extraction produced no transcript, scenes, or keyframes. "
            "The pipeline cannot generate grounded documentation from empty data. "
            "Check that the video file is valid and processing mode is correct."
        )
        logger.error("pipeline.empty_extraction", video_source=request.video_source, mode=mode)
        raise RuntimeError(msg)

    # Stage 3: Structure
    logger.info("pipeline.stage", stage="structure")
    structure_agent = StructureAgent(client)
    outline = await structure_agent.process(
        extraction_result, request.doc_type, request.supplementary_context, request.metadata
    )

    # Stage 4: Writer
    logger.info("pipeline.stage", stage="writer")
    writer_agent = WriterAgent(client)
    document = await writer_agent.process(outline, extraction_result)

    # Stage 5: Editor
    logger.info("pipeline.stage", stage="editor")
    editor_agent = EditorAgent(client)
    document = await editor_agent.process(document)

    # Stage 6: Evaluate
    logger.info("pipeline.stage", stage="evaluate")
    evaluate_agent = EvaluateAgent(client)
    evaluation = await evaluate_agent.process(document, extraction_result)

    # Optional: Re-edit if evaluation fails (up to MAX_REVISION_ITERATIONS)
    iteration = 1
    while not evaluation.passed and iteration < MAX_REVISION_ITERATIONS:
        iteration += 1
        logger.info("pipeline.revision", iteration=iteration, score=evaluation.scores.overall)

        # Feed evaluation suggestions back to editor
        feedback = "\n".join(
            f"- [{s.dimension}] {s.issue}: {s.suggestion}" for s in evaluation.suggestions
        )
        document = await editor_agent.process(document, feedback=feedback)
        evaluation = await evaluate_agent.process(document, extraction_result)

    logger.info(
        "pipeline.complete",
        doc_id=document.document_id,
        passed=evaluation.passed,
        score=evaluation.scores.overall,
        iterations=iteration,
    )

    return PipelineResult(
        document=document,
        evaluation=evaluation,
        extraction=extraction_result,
    )
