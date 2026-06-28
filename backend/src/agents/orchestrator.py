"""Pipeline Orchestrator — coordinates the 6-agent documentation pipeline."""

from __future__ import annotations

from pathlib import Path
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
from src.services.learn_mcp_tools import LEARN_MCP_SERVER, LearnMCPTools
from src.services.mcp_client import MCPClientManager, MCPServerConfig, MCPTransportType

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
    supplementary_context: str = Field(default="", description="Additional context (README, API specs, etc.)")
    workiq_context: str = Field(default="", description="Pre-fetched M365 context from Work IQ")
    supplementary_documents: list[str] = Field(
        default_factory=list,
        description="Paths to supplementary document files (.docx, .pdf, .pptx) to convert and include",
    )
    metadata: DocumentMetadata | None = Field(default=None, description="User-provided frontmatter metadata")


def create_foundry_client() -> FoundryChatClient:
    """Create a FoundryChatClient using DefaultAzureCredential."""
    settings = get_settings()
    return FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model,
        credential=DefaultAzureCredential(),
    )


def resolve_extraction_mode(
    requested_mode: ProcessingMode | None = None,
) -> ProcessingMode:
    """Resolve which extraction PATH to use (Video Indexer cloud vs local FFmpeg/Whisper).

    - explicit cloud/local -> that mode
    - otherwise honor settings.processing_mode: cloud/local explicit, or
      auto -> CLOUD when Foundry AND Video Indexer are configured, else LOCAL.
    """
    settings = get_settings()

    if requested_mode is not None:
        return requested_mode

    if settings.processing_mode == "cloud":
        return ProcessingMode.CLOUD
    if settings.processing_mode == "local":
        return ProcessingMode.LOCAL

    # auto
    if settings.foundry_available and settings.video_indexer_available:
        logger.info("pipeline.auto_extraction", path="cloud", reason="foundry+video_indexer configured")
        return ProcessingMode.CLOUD

    logger.info("pipeline.auto_extraction", path="local", reason="foundry or video_indexer not configured")
    return ProcessingMode.LOCAL


def create_extraction_client():
    """Create the client used for keyframe vision analysis during extraction.

    Prefers Azure Foundry (best vision); falls back to Copilot proxy; else None
    (extraction proceeds without vision descriptions).
    """
    settings = get_settings()

    if settings.foundry_available:
        logger.info("extraction.vision_client", client="foundry")
        return create_foundry_client()

    if settings.copilot_proxy_available:
        logger.info("extraction.vision_client", client="copilot_proxy")
        return create_copilot_client(
            settings.copilot_proxy_url,
            model=settings.copilot_proxy_model,
            secret=settings.copilot_proxy_secret,
        )

    logger.warning("extraction.vision_client", client="none", reason="no foundry or copilot proxy configured")
    return None


def create_llm_client(
    processing_mode: ProcessingMode | None = None,
    *,
    model_override: str | None = None,
):
    """Create the LLM client for downstream agents (structure, writer, editor, evaluate).

    Rules:
    - ``processing_mode=CLOUD`` (explicit) → Azure AI Foundry.
    - ``processing_mode=LOCAL`` (explicit) → Copilot proxy if available, else warn + Foundry.
    - No mode supplied → consult ``settings.processing_mode``:
      - ``"cloud"`` → Foundry
      - ``"local"`` → Copilot proxy if available else warn + Foundry
      - ``"auto"`` → Copilot proxy if available, else Foundry
    """
    settings = get_settings()

    copilot_model = model_override or settings.copilot_proxy_model

    # --- Explicit mode from request ---
    if processing_mode == ProcessingMode.CLOUD:
        logger.info("pipeline.using_foundry", reason="processing_mode=cloud")
        return create_foundry_client()

    if processing_mode == ProcessingMode.LOCAL:
        if settings.copilot_proxy_available:
            logger.info(
                "pipeline.using_copilot_proxy",
                proxy_url=settings.copilot_proxy_url,
                model=copilot_model,
                model_override=model_override,
            )
            return create_copilot_client(
                settings.copilot_proxy_url,
                model=copilot_model,
                secret=settings.copilot_proxy_secret,
            )
        logger.warning(
            "pipeline.local_mode_no_proxy",
            reason="processing_mode=local but copilot_proxy_url is not configured; falling back to Foundry",
        )
        return create_foundry_client()

    # --- No explicit mode: resolve from settings ---
    if settings.processing_mode == "cloud":
        logger.info("pipeline.using_foundry", reason="settings.processing_mode=cloud")
        return create_foundry_client()

    if settings.processing_mode == "local":
        if settings.copilot_proxy_available:
            logger.info(
                "pipeline.using_copilot_proxy",
                proxy_url=settings.copilot_proxy_url,
                model=copilot_model,
                model_override=model_override,
            )
            return create_copilot_client(
                settings.copilot_proxy_url,
                model=copilot_model,
                secret=settings.copilot_proxy_secret,
            )
        logger.warning(
            "pipeline.local_mode_no_proxy",
            reason="settings.processing_mode=local but copilot_proxy_url is not configured; falling back to Foundry",
        )
        return create_foundry_client()

    # auto: prefer Copilot proxy for downstream, fall back to Foundry
    if settings.copilot_proxy_available:
        logger.info(
            "pipeline.using_copilot_proxy",
            proxy_url=settings.copilot_proxy_url,
            model=copilot_model,
            model_override=model_override,
            reason="auto mode, copilot proxy available",
        )
        return create_copilot_client(
            settings.copilot_proxy_url,
            model=copilot_model,
            secret=settings.copilot_proxy_secret,
        )

    logger.info("pipeline.using_foundry", reason="auto mode, no copilot proxy")
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
    extraction_mode = resolve_extraction_mode(request.processing_mode)
    downstream_client = create_llm_client(request.processing_mode)
    extraction_client = create_extraction_client()

    logger.info(
        "pipeline.start",
        source=request.video_source,
        doc_type=request.doc_type,
        extraction_mode=extraction_mode,
        downstream_client=type(downstream_client).__name__,
    )

    # Create MCP client for documentation grounding
    learn_server = MCPServerConfig(
        name=LEARN_MCP_SERVER,
        transport_type=MCPTransportType.STREAMABLE_HTTP,
        endpoint=settings.mcp_learn_endpoint,
        enabled=bool(settings.mcp_learn_endpoint),
    )
    mcp_manager = MCPClientManager(
        servers={LEARN_MCP_SERVER: learn_server},
        cache_ttl=settings.mcp_cache_ttl_seconds,
        request_timeout=settings.mcp_request_timeout_seconds,
        graceful_degradation=settings.mcp_graceful_degradation,
    )
    learn_tools = LearnMCPTools(mcp_manager)

    try:
        # Stage 1: Ingestion
        logger.info("pipeline.stage", stage="ingestion")
        ingestion_agent = IngestionAgent()
        ingestion_result = await ingestion_agent.process(request.video_source, extraction_mode)

        # Stage 2: Extraction
        logger.info("pipeline.stage", stage="extraction")
        extraction_agent = ExtractionAgent(foundry_client=extraction_client)
        extraction_result = await extraction_agent.process(ingestion_result.metadata, extraction_mode)

        # Validate extraction produced meaningful data
        if not extraction_result.transcript and not extraction_result.scenes and not extraction_result.keyframes:
            msg = (
                "Extraction produced no transcript, scenes, or keyframes. "
                "The pipeline cannot generate grounded documentation from empty data. "
                "Check that the video file is valid and processing mode is correct."
            )
            logger.error("pipeline.empty_extraction", video_source=request.video_source, mode=extraction_mode)
            raise RuntimeError(msg)

        # Convert supplementary documents to Markdown
        if request.supplementary_documents:
            from src.services.document_converter import DocumentConversionError, DocumentConverter

            converter = DocumentConverter()
            converted_parts = []
            for doc_path in request.supplementary_documents:
                try:
                    converted = converter.convert(doc_path)
                    converted_parts.append(f"## Supplementary: {Path(doc_path).name}\n\n{converted.markdown}")
                    logger.info(
                        "pipeline.supplementary_converted",
                        path=Path(doc_path).name,
                        words=converted.word_count,
                    )
                except (ValueError, DocumentConversionError, FileNotFoundError) as e:
                    logger.warning(
                        "pipeline.supplementary_conversion_failed",
                        path=Path(doc_path).name,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            if converted_parts:
                extra_context = "\n\n---\n\n".join(converted_parts)
                if request.supplementary_context:
                    request.supplementary_context += "\n\n---\n\n" + extra_context
                else:
                    request.supplementary_context = extra_context

        # Merge Work IQ context into supplementary context
        if request.workiq_context:
            logger.info("pipeline.workiq_context", length=len(request.workiq_context))
            workiq_section = f"## M365 Context (via Work IQ)\n\n{request.workiq_context}"
            if request.supplementary_context:
                request.supplementary_context += "\n\n---\n\n" + workiq_section
            else:
                request.supplementary_context = workiq_section

        # Stage 3: Structure
        logger.info("pipeline.stage", stage="structure")
        structure_agent = StructureAgent(downstream_client, learn_tools=learn_tools)
        outline = await structure_agent.process(
            extraction_result, request.doc_type, request.supplementary_context, request.metadata
        )

        # Stage 4: Writer
        logger.info("pipeline.stage", stage="writer")
        writer_agent = WriterAgent(downstream_client, learn_tools=learn_tools)
        document = await writer_agent.process(
            outline,
            extraction_result,
            supplementary_context=request.supplementary_context,
        )

        # Stage 5: Editor
        logger.info("pipeline.stage", stage="editor")
        editor_agent = EditorAgent(downstream_client, learn_tools=learn_tools)
        document = await editor_agent.process(document, extraction=extraction_result)

        # Stage 6: Evaluate
        logger.info("pipeline.stage", stage="evaluate")
        evaluate_agent = EvaluateAgent(downstream_client)
        evaluation = await evaluate_agent.process(document, extraction_result)

        # Optional: Re-edit if evaluation fails (up to MAX_REVISION_ITERATIONS)
        iteration = 1
        while not evaluation.passed and iteration < MAX_REVISION_ITERATIONS:
            iteration += 1
            logger.info("pipeline.revision", iteration=iteration, score=evaluation.scores.overall)

            # Feed evaluation suggestions back to editor
            feedback = "\n".join(f"- [{s.dimension}] {s.issue}: {s.suggestion}" for s in evaluation.suggestions)
            document = await editor_agent.process(
                document,
                feedback=feedback,
                extraction=extraction_result,
            )
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
    finally:
        await mcp_manager.close()
