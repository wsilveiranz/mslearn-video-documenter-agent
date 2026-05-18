"""API route definitions for the Video Documenter backend."""

from __future__ import annotations

import importlib
import os
import secrets
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.agents.editor import EditorAgent
from src.agents.evaluate import EvaluateAgent
from src.agents.extraction import ExtractionAgent
from src.agents.ingestion import IngestionAgent
from src.agents.orchestrator import MAX_REVISION_ITERATIONS, create_llm_client
from src.agents.structure import StructureAgent
from src.agents.writer import WriterAgent
from src.api.websocket import manager
from src.config import get_settings
from src.models.document import DocType, DocumentMetadata
from src.models.evaluation import EvaluationReport
from src.models.services import AZURE_SERVICES
from src.models.video import DataQualityReport, ExtractionResult, ProcessingMode, ProcessingStatus, VideoJob

if TYPE_CHECKING:
    from src.models.document import GeneratedDocument

logger = structlog.get_logger()
router = APIRouter(tags=["Video Documenter"])

# ---- In-memory storage (Phase 1) ----
_video_jobs: dict[str, VideoJob] = {}
_documents: dict[str, GeneratedDocument] = {}
_extractions: dict[str, ExtractionResult] = {}
_evaluations: dict[str, EvaluationReport] = {}

# ---- Session auth ----
_session_secret: str = secrets.token_hex(32)
_secret_retrieved: bool = False
_bootstrap_token: str | None = os.environ.get("VD_BOOTSTRAP_TOKEN")


def _require_session_auth(request: Request) -> None:
    """Validate the session secret header on sensitive endpoints."""
    token = request.headers.get("X-Session-Secret")
    if token != _session_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing session secret.")


# ---- Request/Response Models ----

class IngestResponse(BaseModel):
    video_id: str
    status: ProcessingStatus
    message: str


class GenerateRequest(BaseModel):
    video_id: str
    doc_type: DocType
    supplementary_context: str = ""
    metadata: DocumentMetadata | None = None
    model: str | None = None


class GenerateResponse(BaseModel):
    document_id: str
    status: str
    message: str


class ExtractionResponse(BaseModel):
    video_id: str
    status: str
    message: str


class RefineRequest(BaseModel):
    feedback: str
    model: str | None = None
    enrich_m365: bool = False


class ExtractionSummary(BaseModel):
    transcript_segments: int
    scenes: int
    keyframes: int
    has_vision_descriptions: bool


class StatusResponse(BaseModel):
    video_id: str
    status: ProcessingStatus
    step: int
    total_steps: int
    current_stage: str
    progress_detail: str = ""
    document_id: str | None = None
    extraction_summary: ExtractionSummary | None = None
    data_quality: DataQualityReport | None = None


class MediaFileResponse(BaseModel):
    filename: str
    output_path: str
    alt_text: str


class EvalScoreResponse(BaseModel):
    completeness: float
    accuracy: float
    style_compliance: float
    readability: float
    grounding: float
    overall: float
    passed: bool


class DocumentResponse(BaseModel):
    document_id: str
    doc_type: DocType
    markdown_content: str
    word_count: int
    revision_number: int
    media_files: list[MediaFileResponse] = []
    eval_scores: EvalScoreResponse | None = None



class LmProxyConfigRequest(BaseModel):
    proxy_url: str
    proxy_secret: str = ""


class LmProxyConfigResponse(BaseModel):
    status: str
    message: str


class ModelOverrideRequest(BaseModel):
    """Optional body for endpoints that accept a model override."""

    model: str | None = None


@router.post("/config/lm-proxy", response_model=LmProxyConfigResponse)
async def register_lm_proxy(request: LmProxyConfigRequest) -> LmProxyConfigResponse:
    """Register the VS Code Copilot LM Proxy URL for local-mode LLM routing."""
    proxy_url = request.proxy_url.rstrip("/")

    # Only allow localhost connections for security
    parsed = urlparse(proxy_url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(
            status_code=400,
            detail="LM Proxy URL must be a localhost address (http://localhost, http://127.0.0.1, or http://[::1])",
        )

    # Always update — the proxy port may change between extension restarts
    settings = get_settings()
    settings.copilot_proxy_url = proxy_url
    settings.copilot_proxy_secret = request.proxy_secret

    logger.info("config.lm_proxy_registered", proxy_url=proxy_url)

    return LmProxyConfigResponse(
        status="ok",
        message="LM Proxy URL registered",
    )


# ---- Health ----

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "video-documenter"}


@router.get("/health/deep")
async def health_deep() -> dict[str, object]:
    """Deep health check — validates the full Azure async import chain.

    Used by the VSIX build smoke test to catch missing PyInstaller hidden
    imports at build time.  Does NOT require Azure credentials or env vars.
    """
    critical_modules: list[str | tuple[str, str]] = [
        "aiohttp",
        "multidict",
        "yarl",
        "frozenlist",
        "aiosignal",
        "charset_normalizer",
        "azure.core.pipeline.transport._aiohttp",
        "azure.ai.projects.aio",
        "azure.ai.inference.aio",
        ("agent_framework_foundry", "FoundryChatClient"),
        ("azure.identity.aio", "DefaultAzureCredential"),
    ]

    for entry in critical_modules:
        if isinstance(entry, tuple):
            module_name, attr = entry
        else:
            module_name, attr = entry, None

        try:
            mod = importlib.import_module(module_name)
            if attr is not None:
                getattr(mod, attr)
        except Exception as exc:
            logger.error(
                "health.deep_failed",
                missing_module=module_name,
                error=str(exc),
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "status": "error",
                    "missing_module": module_name,
                    "error": str(exc),
                },
            ) from exc

    return {"status": "ok", "imports_verified": len(critical_modules)}


# ---- Session Auth ----

@router.get("/auth/session-secret")
async def get_session_secret(request: Request):
    """Return the session secret. Requires bootstrap token and is only callable once."""
    global _secret_retrieved
    if _secret_retrieved:
        raise HTTPException(status_code=403, detail="Session secret already retrieved.")

    # Require the bootstrap token that was passed via env var at process start
    provided_token = request.headers.get("X-Bootstrap-Token")
    if not _bootstrap_token or provided_token != _bootstrap_token:
        raise HTTPException(status_code=403, detail="Invalid or missing bootstrap token.")

    _secret_retrieved = True
    return {"secret": _session_secret}


# ---- Services ----

@router.get("/services")
async def list_services() -> list[dict[str, str]]:
    """Return the list of common Azure service slugs for ms.service metadata."""
    return [{"slug": slug, "display_name": name} for slug, name in AZURE_SERVICES]


# ---- Intent Classification ----

class ClassifyIntentRequest(BaseModel):
    message: str


@router.post("/classify-intent")
async def classify_intent_endpoint(request: ClassifyIntentRequest) -> dict:
    """Classify a user message into an actionable intent."""
    from src.services.intent_classifier import classify_intent, classify_intent_fast

    # Fast path first (no LLM needed)
    fast = classify_intent_fast(request.message)
    if fast is not None:
        return fast.model_dump()

    # LLM classification
    try:
        client = create_llm_client()
        result = await classify_intent(request.message, client)
        return result.model_dump()
    except Exception as e:
        logger.error(
            "classify_intent_failed",
            operation="intent_classification",
            error=str(e),
            exc_info=True,
        )
        return {"intent": "refine", "confidence": "fallback", "raw_response": None}


# ---- Background task helpers ----

async def _run_ingestion(video_id: str, source: str, *, is_temp_file: bool = False) -> None:
    """Run ingestion in the background and update the video job."""
    job = _video_jobs[video_id]
    try:
        job.status = ProcessingStatus.INGESTING
        job.current_stage = "ingestion"
        job.step = 1
        manager.send_progress(video_id, "ingestion", 1, 6, "Step 1/6: Ingesting video...")

        settings = get_settings()
        mode = ProcessingMode(settings.processing_mode)
        agent = IngestionAgent()
        result = await agent.process(source, mode)

        job.extraction_result = None
        job.status = ProcessingStatus.QUEUED
        job.current_stage = "ingestion_complete"
        # Store ingestion output separately — keep job.video_id stable
        job.ingestion_video_id = result.video_id
        job.source_path = result.metadata.source_path
        job.video_metadata = result.metadata

        logger.info("api.ingestion_complete", video_id=video_id, ingestion_id=result.video_id)
        manager.send_progress(video_id, "ingestion_complete", 1, 6, "Step 1/6: Ingestion complete ✓")
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.ingestion_failed", video_id=video_id, error=repr(exc), exc_info=True)
        manager.send_progress(video_id, "failed", job.step, 6, str(exc))
    finally:
        if is_temp_file:
            try:
                Path(source).unlink(missing_ok=True)
            except OSError:
                logger.warning("api.temp_cleanup_failed", path=source)


async def _run_extraction(video_id: str) -> None:
    """Run content extraction in the background and update the video job."""
    job = _video_jobs[video_id]
    try:
        if job.current_stage not in ("ingestion_complete", "extraction_complete"):
            raise RuntimeError(
                f"Cannot extract: video job is at stage '{job.current_stage}', expected 'ingestion_complete'"
            )

        job.status = ProcessingStatus.PROCESSING
        job.current_stage = "extracting"
        job.step = 2
        manager.send_progress(video_id, "extracting", 2, 6, "Step 2/6: Extracting transcript, scenes, and keyframes...")

        settings = get_settings()
        mode = ProcessingMode(settings.processing_mode)
        client = create_llm_client(mode, model_override=job.llm_model)
        extraction_agent = ExtractionAgent(foundry_client=client)

        # Reuse cached metadata from ingestion to avoid re-probing the video
        if job.video_metadata is not None:
            video_metadata = job.video_metadata
        else:
            ingestion_agent = IngestionAgent()
            ingestion_result = await ingestion_agent.process(job.source_path or "", mode)
            video_metadata = ingestion_result.metadata

        async def _on_extraction_progress(progress: str) -> None:
            if progress and progress != "Processing...":
                detail = f"Video Indexer processing... {progress}"
            else:
                detail = "Video Indexer processing..."
            job.progress_detail = detail
            manager.send_progress(video_id, "extracting", 2, 6, detail)

        extraction_result = await extraction_agent.process(
            video_metadata, mode, on_progress=_on_extraction_progress
        )

        if not extraction_result.transcript and not extraction_result.scenes and not extraction_result.keyframes:
            logger.error(
                "api.extraction_empty",
                video_id=video_id,
                operation="extraction",
                detail="Extraction produced no transcript, scenes, or keyframes",
            )
            job.status = ProcessingStatus.FAILED
            job.error_message = (
                "Extraction produced no transcript, scenes, or keyframes. "
                "The video may be unreadable or unsupported."
            )
            manager.send_progress(
                video_id, "failed", 2, 6,
                "Extraction failed: no content could be extracted from the video.",
            )
            manager.clear_progress(video_id)
            return
        else:
            job.extraction_result = extraction_result
            job.current_stage = "extraction_complete"
            job.status = ProcessingStatus.QUEUED

            logger.info("api.extraction_complete", video_id=video_id)
            manager.send_progress(video_id, "extraction_complete", 2, 6, "Step 2/6: Extraction complete ✓")
            manager.clear_progress(video_id)
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.extraction_failed", video_id=video_id, error=repr(exc), exc_info=True)
        manager.send_progress(video_id, "failed", job.step, 6, str(exc))
        manager.clear_progress(video_id)


async def _create_learn_tools():
    """Create MCP client + LearnMCPTools for the API pipeline.

    Returns (mcp_manager, learn_tools) where learn_tools may be None if
    MCP is not configured.  Caller must ``await mcp_manager.close()``
    when done.
    """
    from src.services.learn_mcp_tools import LEARN_MCP_SERVER, LearnMCPTools
    from src.services.mcp_client import MCPClientManager, MCPServerConfig, MCPTransportType

    settings = get_settings()
    if not settings.mcp_learn_endpoint:
        return None, None

    learn_server = MCPServerConfig(
        name=LEARN_MCP_SERVER,
        transport_type=MCPTransportType.STREAMABLE_HTTP,
        endpoint=settings.mcp_learn_endpoint,
        enabled=True,
    )
    mcp_manager = MCPClientManager(
        servers={LEARN_MCP_SERVER: learn_server},
        cache_ttl=settings.mcp_cache_ttl_seconds,
        request_timeout=settings.mcp_request_timeout_seconds,
        graceful_degradation=settings.mcp_graceful_degradation,
    )
    learn_tools = LearnMCPTools(mcp_manager)
    return mcp_manager, learn_tools


async def _run_pipeline(
    video_id: str, doc_type: DocType, supplementary_context: str, metadata: DocumentMetadata | None = None,
) -> None:
    """Run the full pipeline in the background with per-stage progress updates."""
    job = _video_jobs.get(video_id)
    if job is None:
        return

    mcp_manager = None
    try:
        settings = get_settings()
        mode = ProcessingMode(settings.processing_mode)
        client = create_llm_client(mode, model_override=job.llm_model)
        job.status = ProcessingStatus.PROCESSING

        # Create MCP tools for documentation grounding
        mcp_manager, learn_tools = await _create_learn_tools()

        # Check if extraction was already done (e.g., by /extract endpoint)
        if job.extraction_result is not None:
            extraction_result = job.extraction_result
            logger.info("pipeline.using_cached_extraction", video_id=video_id)
            manager.send_progress(video_id, "extracting", 2, 6, "Step 2/6: Using cached extraction ✓")
        else:
            job.current_stage = "extracting"
            job.step = 2
            manager.send_progress(
                video_id, "extracting", 2, 6, "Step 2/6: Extracting transcript, scenes, and keyframes...",
            )

            extraction_agent = ExtractionAgent(foundry_client=client)

            # Reuse cached metadata from ingestion to avoid re-probing the video
            if job.video_metadata is not None:
                video_metadata = job.video_metadata
            else:
                ingestion_agent = IngestionAgent()
                ingestion_result = await ingestion_agent.process(job.source_path or "", mode)
                video_metadata = ingestion_result.metadata

            async def _on_pipeline_extraction_progress(progress: str) -> None:
                if progress and progress != "Processing...":
                    detail = f"Video Indexer processing... {progress}"
                else:
                    detail = "Video Indexer processing..."
                job.progress_detail = detail
                manager.send_progress(video_id, "extracting", 2, 6, detail)

            extraction_result = await extraction_agent.process(
                video_metadata, mode, on_progress=_on_pipeline_extraction_progress
            )

            if not extraction_result.transcript and not extraction_result.scenes and not extraction_result.keyframes:
                raise RuntimeError("Extraction produced no transcript, scenes, or keyframes.")

            job.extraction_result = extraction_result
            manager.send_progress(video_id, "extracting", 2, 6, "Step 2/6: Extraction complete ✓")

        # Reset stale extraction progress detail before moving to subsequent stages
        job.progress_detail = ""

        # Step 3/6: Structure
        job.current_stage = "structuring"
        job.step = 3
        manager.send_progress(video_id, "structuring", 3, 6, "Step 3/6: Creating document outline...")

        structure_agent = StructureAgent(client, learn_tools=learn_tools)
        outline = await structure_agent.process(extraction_result, doc_type, supplementary_context, metadata)

        manager.send_progress(video_id, "structuring", 3, 6, "Step 3/6: Outline ready ✓")

        # Step 4/6: Writer
        job.current_stage = "writing"
        job.step = 4
        manager.send_progress(video_id, "writing", 4, 6, "Step 4/6: Writing document...")

        writer_agent = WriterAgent(client, learn_tools=learn_tools)
        document = await writer_agent.process(
            outline, extraction_result,
            quality_report=job.quality_report,
            supplementary_context=supplementary_context,
        )

        manager.send_progress(video_id, "writing", 4, 6, "Step 4/6: Draft complete ✓")

        # Step 5/6: Editor
        job.current_stage = "editing"
        job.step = 5
        manager.send_progress(video_id, "editing", 5, 6, "Step 5/6: Editing for MS Learn style...")

        editor_agent = EditorAgent(client, learn_tools=learn_tools)
        document = await editor_agent.process(document, extraction=extraction_result)

        manager.send_progress(video_id, "editing", 5, 6, "Step 5/6: Editing complete ✓")

        # Step 6/6: Evaluate
        job.current_stage = "evaluating"
        job.step = 6
        manager.send_progress(video_id, "evaluating", 6, 6, "Step 6/6: Quality evaluation...")

        evaluate_agent = EvaluateAgent(client)
        evaluation = await evaluate_agent.process(document, extraction_result, quality_report=job.quality_report)

        # Revision loop — keep step at 6 (still in evaluate phase)
        iteration = 1
        while not evaluation.passed and iteration < MAX_REVISION_ITERATIONS:
            iteration += 1
            manager.send_progress(
                video_id, "evaluating", 6, 6, f"Step 6/6: Revision {iteration} — re-editing..."
            )
            feedback = "\n".join(
                f"- [{s.dimension}] {s.issue}: {s.suggestion}" for s in evaluation.suggestions
            )
            document = await editor_agent.process(document, feedback=feedback, extraction=extraction_result)
            evaluation = await evaluate_agent.process(document, extraction_result, quality_report=job.quality_report)

        # Done
        result_doc_id = document.document_id
        _documents[result_doc_id] = document
        _extractions[result_doc_id] = extraction_result
        _evaluations[result_doc_id] = evaluation

        job.document_id = result_doc_id
        job.status = ProcessingStatus.COMPLETED
        job.current_stage = "completed"

        logger.info(
            "api.pipeline_complete",
            video_id=video_id,
            doc_id=result_doc_id,
            passed=evaluation.passed,
            score=evaluation.scores.overall,
        )
        manager.send_progress(video_id, "completed", 6, 6, "Document generated!")
        manager.clear_progress(video_id)
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.pipeline_failed", video_id=video_id, error=repr(exc), exc_info=True)
        manager.send_progress(video_id, "failed", job.step, 6, str(exc))
        manager.clear_progress(video_id)
    finally:
        if mcp_manager is not None:
            await mcp_manager.close()

@router.post("/videos/ingest", response_model=IngestResponse)
async def ingest_video(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = None,
    video_path: str | None = Form(None),
    model: str | None = Form(None),
) -> IngestResponse:
    """Upload or register a video for processing.

    Accepts either a file upload or a file path/URL.
    """
    if file is None and video_path is None:
        raise HTTPException(status_code=400, detail="Provide either a file upload or video_path")

    is_temp_file = False
    if file is not None:
        settings = get_settings()
        max_bytes = settings.max_video_size_mb * 1024 * 1024
        suffix = Path(file.filename).suffix if file.filename else ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            bytes_written = 0
            while chunk := await file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    tmp.close()
                    Path(tmp.name).unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds {settings.max_video_size_mb} MB limit.",
                    )
                tmp.write(chunk)
            source = tmp.name
        is_temp_file = True
    else:
        source = video_path  # type: ignore[assignment]

    video_id = uuid.uuid4().hex[:12]

    logger.info("api.ingest", source=source, video_id=video_id)

    job = VideoJob(video_id=video_id, status=ProcessingStatus.QUEUED, llm_model=model)
    _video_jobs[video_id] = job

    background_tasks.add_task(_run_ingestion, video_id, source, is_temp_file=is_temp_file)

    return IngestResponse(
        video_id=video_id,
        status=ProcessingStatus.QUEUED,
        message=f"Video '{Path(source).name}' queued for ingestion.",
    )


@router.get("/videos/{video_id}/status", response_model=StatusResponse)
async def get_video_status(video_id: str) -> StatusResponse:
    """Check the processing status of a video."""
    job = _video_jobs.get(video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{video_id}' not found")

    extraction_summary = None
    if job.extraction_result is not None:
        extraction_summary = ExtractionSummary(
            transcript_segments=len(job.extraction_result.transcript),
            scenes=len(job.extraction_result.scenes),
            keyframes=len(job.extraction_result.keyframes),
            has_vision_descriptions=any(kf.ui_description for kf in job.extraction_result.keyframes),
        )

    return StatusResponse(
        video_id=job.video_id,
        status=job.status,
        step=job.step,
        total_steps=job.total_steps,
        current_stage=job.current_stage,
        progress_detail=job.progress_detail,
        document_id=job.document_id,
        extraction_summary=extraction_summary,
        data_quality=job.quality_report,
    )


@router.post("/videos/{video_id}/extract", response_model=ExtractionResponse)
async def extract_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    body: ModelOverrideRequest | None = None,
) -> ExtractionResponse:
    """Trigger content extraction (transcript, scenes, keyframes) for an ingested video."""
    job = _video_jobs.get(video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{video_id}' not found")

    if body and body.model:
        job.llm_model = body.model

    if job.status == ProcessingStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Video job '{video_id}' has failed: {job.error_message}")

    # Allow re-extraction or first-time extraction
    if job.current_stage not in ("ingestion_complete", "extraction_complete"):
        raise HTTPException(
            status_code=400,
            detail=f"Video job '{video_id}' is not ready for extraction (stage: {job.current_stage})",
        )

    logger.info("api.extract", video_id=video_id)
    background_tasks.add_task(_run_extraction, video_id)

    return ExtractionResponse(
        video_id=video_id,
        status="queued",
        message="Extraction queued.",
    )


@router.get("/videos/{video_id}/extraction")
async def get_extraction_results(video_id: str) -> dict:
    """Get extraction results for a processed video."""
    job = _video_jobs.get(video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{video_id}' not found")

    if job.extraction_result is None:
        raise HTTPException(status_code=404, detail="Extraction not yet complete")

    return job.extraction_result.model_dump()


@router.post("/videos/{video_id}/assess-quality", response_model=DataQualityReport)
async def assess_quality(video_id: str, body: ModelOverrideRequest | None = None) -> DataQualityReport:
    """Run LLM-based quality assessment on extraction data."""
    job = _video_jobs.get(video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{video_id}' not found")

    if body and body.model:
        job.llm_model = body.model

    if job.extraction_result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Extraction not yet complete for video '{video_id}'. Run extraction first.",
        )

    # Return cached report if available
    if job.quality_report is not None:
        logger.info("api.assess_quality_cached", video_id=video_id)
        return job.quality_report

    logger.info("api.assess_quality", video_id=video_id)

    try:
        from src.agents.orchestrator import create_llm_client
        from src.agents.quality import QualityAssessmentAgent

        client = create_llm_client(model_override=job.llm_model)
        quality_agent = QualityAssessmentAgent(client)
        report = await quality_agent.process(job.extraction_result)

        job.quality_report = report
        return report
    except Exception as exc:
        logger.error(
            "api.assess_quality_failed",
            video_id=video_id,
            error=repr(exc),
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Quality assessment failed: {exc}") from exc


# ---- Document Endpoints ----

@router.post("/documents/generate", response_model=GenerateResponse)
async def generate_document(request: GenerateRequest, background_tasks: BackgroundTasks) -> GenerateResponse:
    """Generate an MS Learn document from a processed video."""
    job = _video_jobs.get(request.video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{request.video_id}' not found")

    if job.status == ProcessingStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Video job '{request.video_id}' has failed: {job.error_message}")

    if job.current_stage not in ("ingestion_complete", "extraction_complete"):
        raise HTTPException(
            status_code=400,
            detail=f"Video job '{request.video_id}' is not ready for generation (stage: {job.current_stage})",
        )

    if request.model:
        job.llm_model = request.model

    logger.info("api.generate", video_id=request.video_id, doc_type=request.doc_type, llm_model=job.llm_model)

    background_tasks.add_task(
        _run_pipeline, request.video_id, request.doc_type, request.supplementary_context, request.metadata
    )

    return GenerateResponse(
        document_id="pending",
        status="queued",
        message=f"Document generation for '{request.doc_type.value}' queued.",
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str) -> DocumentResponse:
    """Get a generated document by ID."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    media_files = [
        MediaFileResponse(
            filename=Path(s.output_path).name if s.output_path else Path(s.source_path).name,
            output_path=s.output_path or f"./media/{Path(s.source_path).name}",
            alt_text=s.alt_text,
        )
        for s in doc.media_files
    ]

    # Include eval scores if available
    eval_scores = None
    evaluation = _evaluations.get(document_id)
    if evaluation:
        s = evaluation.scores
        eval_scores = EvalScoreResponse(
            completeness=s.completeness,
            accuracy=s.accuracy,
            style_compliance=s.style_compliance,
            readability=s.readability,
            grounding=s.grounding,
            overall=s.overall,
            passed=s.passed,
        )

    return DocumentResponse(
        document_id=doc.document_id,
        doc_type=doc.doc_type,
        markdown_content=doc.markdown_content,
        word_count=doc.word_count,
        revision_number=doc.revision_number,
        media_files=media_files,
        eval_scores=eval_scores,
    )


@router.get("/documents/{document_id}/media/{filename}")
async def download_media(document_id: str, filename: str) -> FileResponse:
    """Download a media file associated with a document by filename."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    for screenshot in doc.media_files:
        mf_name = (
            Path(screenshot.output_path).name
            if screenshot.output_path
            else Path(screenshot.source_path).name
        )
        if mf_name == filename:
            source = Path(screenshot.source_path)
            if not source.is_file():
                raise HTTPException(status_code=404, detail="Media file not found on disk")
            return FileResponse(path=str(source), filename=filename)

    raise HTTPException(status_code=404, detail=f"Media file '{filename}' not found in document")


async def _fetch_m365_context_for_doc(doc: GeneratedDocument, user_feedback: str) -> str:
    """Build a smart query from the document context and fetch M365 content via Work IQ.

    Returns the M365 summary text, or empty string if unavailable/disabled.
    """
    from src.services.mcp_client import MCPClientManager, MCPServerConfig, MCPTransportType
    from src.services.workiq_mcp_tools import WORKIQ_MCP_SERVER, WorkIQTools

    settings = get_settings()
    if not settings.mcp_workiq_enabled:
        logger.info("m365_enrich.disabled")
        return ""

    # Build a targeted query from document metadata + user intent
    query_parts: list[str] = []

    # Extract title from YAML frontmatter or first H1
    if doc.markdown_content:
        for line in doc.markdown_content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("title:"):
                query_parts.append(stripped.removeprefix("title:").strip().strip('"').strip("'"))
                break
            if stripped.startswith("# "):
                query_parts.append(stripped.removeprefix("# ").strip())
                break

    # Add the user's feedback intent (strip the M365 trigger words for a cleaner query)
    import re
    clean_feedback = re.sub(
        r"\b(m365|microsoft\s*365|work\s*iq|working\s*documents?|work\s*documents?|"
        r"my\s*documents?|sharepoint|teams\s*messages?|enrich|use|from|with|the|and|to)\b",
        "", user_feedback, flags=re.IGNORECASE,
    ).strip()
    if clean_feedback:
        query_parts.append(clean_feedback)

    query = " ".join(query_parts).strip()
    if not query:
        query = "related documentation and context"

    logger.info("m365_enrich.query", query_length=len(query))

    workiq_server = MCPServerConfig(
        name=WORKIQ_MCP_SERVER,
        transport_type=MCPTransportType.STDIO,
        command=settings.mcp_workiq_npx_path,
        args=["-y", "@microsoft/workiq", "mcp"],
        enabled=True,
    )
    mcp_manager = MCPClientManager(
        servers={WORKIQ_MCP_SERVER: workiq_server},
        cache_ttl=settings.mcp_cache_ttl_seconds,
        request_timeout=settings.mcp_request_timeout_seconds,
        graceful_degradation=settings.mcp_graceful_degradation,
    )

    try:
        tools = WorkIQTools(mcp_manager)
        result = await tools.search_context(query)
        if result.available and result.summary:
            logger.info("m365_enrich.success", query=query, summary_length=len(result.summary))
            return result.summary
        logger.info("m365_enrich.no_results", query=query)
        return ""
    except Exception as exc:
        logger.warning("m365_enrich.failed", query=query, error=str(exc))
        return ""
    finally:
        await mcp_manager.close()


@router.post("/documents/{document_id}/refine", response_model=GenerateResponse)
async def refine_document(
    document_id: str, request: RefineRequest, background_tasks: BackgroundTasks,
    http_request: Request,
) -> GenerateResponse:
    """Iteratively refine a generated document with feedback."""
    # Require session auth when M365 enrichment is requested
    if request.enrich_m365:
        _require_session_auth(http_request)

    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    extraction = _extractions.get(document_id)

    logger.info("api.refine", doc_id=document_id, feedback_length=len(request.feedback))

    async def _refine() -> None:
        # Find associated video_id for WebSocket broadcast
        video_id: str | None = None
        llm_model: str | None = request.model
        for vid, j in _video_jobs.items():
            if j.document_id == document_id:
                video_id = vid
                if not llm_model:
                    llm_model = j.llm_model
                break

        try:
            from src.agents.orchestrator import create_llm_client

            if video_id:
                manager.send_progress(video_id, "refining", 1, 2, "Refining document...")

            # Build the final feedback, enriching with M365 context if requested
            final_feedback = request.feedback

            if request.enrich_m365:
                m365_context = await _fetch_m365_context_for_doc(doc, request.feedback)
                if m365_context:
                    final_feedback = (
                        f"{request.feedback}\n\n"
                        "---\n\n"
                        "## M365 Context (from Work IQ)\n\n"
                        "The following content was retrieved from the user's M365 working documents "
                        "(SharePoint, Teams, emails, meetings). This is authoritative source material — "
                        "integrate it into the article where relevant.\n\n"
                        f"{m365_context}"
                    )
                    if video_id:
                        manager.send_progress(video_id, "refining", 1, 2, "M365 context retrieved. Applying edits...")

            client = create_llm_client(model_override=llm_model)

            # Set up MS Learn MCP tools for style reference during editing
            from src.services.learn_mcp_tools import LEARN_MCP_SERVER, LearnMCPTools
            from src.services.mcp_client import MCPClientManager, MCPServerConfig, MCPTransportType

            settings = get_settings()
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
                editor = EditorAgent(client, learn_tools=learn_tools)
                refined = await editor.process(doc, feedback=final_feedback, extraction=extraction)
            finally:
                await mcp_manager.close()

            if extraction is not None:
                evaluator = EvaluateAgent(client)
                evaluation = await evaluator.process(refined, extraction)
                _evaluations[document_id] = evaluation
                logger.info(
                    "api.refine_evaluated",
                    doc_id=document_id,
                    score=evaluation.scores.overall,
                    passed=evaluation.passed,
                )

            _documents[document_id] = refined
            logger.info("api.refine_complete", doc_id=document_id, revision=refined.revision_number)
            if video_id:
                manager.send_progress(video_id, "refined", 2, 2, "Refinement complete")
                manager.clear_progress(video_id)
        except Exception as exc:
            logger.error("api.refine_failed", doc_id=document_id, error=repr(exc), exc_info=True)
            if video_id:
                manager.send_progress(video_id, "failed", 0, 1, f"Refinement failed: {exc}")
                manager.clear_progress(video_id)

    background_tasks.add_task(_refine)

    return GenerateResponse(
        document_id=document_id,
        status="queued",
        message="Refinement queued.",
    )


# --- Document Conversion Endpoints ---

class ConvertPathRequest(BaseModel):
    path: str


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@router.post("/context/convert-document")
async def convert_document_upload(file: UploadFile):
    """Convert an uploaded document file to Markdown."""
    from src.services.document_converter import DocumentConversionError, DocumentConverter

    # Enforce size limit while reading (don't load unbounded into memory)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1MB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum upload size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    converter = DocumentConverter()
    try:
        result = converter.convert_bytes(content, file.filename or "unknown")
        return result
    except (ValueError, DocumentConversionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("api.convert_document_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Document conversion failed") from e


@router.post("/context/convert-path")
async def convert_document_path(request: ConvertPathRequest, http_request: Request):
    """Convert a local document file to Markdown by path.

    Only converts files with supported document extensions (.docx, .pdf, .pptx, etc.).
    Rejects paths with traversal patterns or unsupported file types to prevent
    arbitrary file reads.
    """
    _require_session_auth(http_request)
    from src.services.document_converter import DocumentConversionError, DocumentConverter

    # Resolve to absolute path and restrict to safe directories
    resolved = Path(request.path).resolve()
    allowed_bases = [
        Path(tempfile.gettempdir()).resolve(),
        Path.home().resolve(),
    ]
    if not any(resolved.is_relative_to(base) for base in allowed_bases):
        raise HTTPException(
            status_code=403,
            detail="Access denied. File must be under the user's home directory or system temp directory.",
        )

    # Only allow supported document extensions (prevents reading arbitrary files)
    converter = DocumentConverter()
    if resolved.suffix.lower() not in converter.supported_extensions():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{resolved.suffix}'. "
                f"Supported: {', '.join(sorted(converter.supported_extensions()))}"
            ),
        )

    try:
        result = converter.convert(str(resolved))
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (ValueError, DocumentConversionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("api.convert_path_failed", path=request.path, error=str(e))
        raise HTTPException(status_code=500, detail="Document conversion failed") from e


# --- M365 Context Search ---

class M365SearchRequest(BaseModel):
    query: str
    video_id: str | None = None


@router.post("/context/search-m365")
async def search_m365_context(request: M365SearchRequest, http_request: Request):
    """Search M365 for supplementary context via Work IQ.

    This endpoint is user-triggered — it should only be called when the
    user explicitly requests M365 context enrichment.
    """
    _require_session_auth(http_request)
    from src.services.mcp_client import MCPClientManager, MCPServerConfig, MCPTransportType
    from src.services.workiq_mcp_tools import WORKIQ_MCP_SERVER, WorkIQTools

    settings = get_settings()

    if not settings.mcp_workiq_enabled:
        raise HTTPException(
            status_code=400,
            detail="Work IQ integration is not enabled. Set MCP_WORKIQ_ENABLED=true.",
        )

    workiq_server = MCPServerConfig(
        name=WORKIQ_MCP_SERVER,
        transport_type=MCPTransportType.STDIO,
        command=settings.mcp_workiq_npx_path,
        args=["-y", "@microsoft/workiq", "mcp"],
        enabled=True,
    )
    mcp_manager = MCPClientManager(
        servers={WORKIQ_MCP_SERVER: workiq_server},
        cache_ttl=settings.mcp_cache_ttl_seconds,
        request_timeout=settings.mcp_request_timeout_seconds,
        graceful_degradation=settings.mcp_graceful_degradation,
    )

    try:
        tools = WorkIQTools(mcp_manager)
        result = await tools.search_context(request.query)

        if not result.available:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Work IQ MCP server is not available. "
                    "Ensure @microsoft/workiq is installed and M365 Copilot is configured."
                ),
            )

        if request.video_id:
            logger.info("api.m365_search", video_id=request.video_id, query_length=len(request.query))

        return result
    finally:
        await mcp_manager.close()
