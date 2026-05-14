"""API route definitions for the Video Documenter backend."""

from __future__ import annotations

import importlib
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
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
    document_id: str | None = None
    extraction_summary: ExtractionSummary | None = None
    data_quality: DataQualityReport | None = None


class DocumentResponse(BaseModel):
    document_id: str
    doc_type: DocType
    markdown_content: str
    word_count: int
    revision_number: int



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
async def health_deep() -> dict:
    """Deep health check — validates the full Azure async import chain.

    Used by the VSIX build smoke test to catch missing PyInstaller hidden
    imports at build time.  Does NOT require Azure credentials or env vars.
    """
    from fastapi.responses import JSONResponse

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
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "missing_module": module_name,
                    "error": str(exc),
                },
            )

    return {"status": "ok", "imports_verified": len(critical_modules)}


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
            manager.send_progress(
                video_id, "extracting", 2, 6,
                f"Step 2/6: Video Indexer processing ({progress})...",
            )

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
            job.error_message = "Extraction produced no transcript, scenes, or keyframes. The video may be unreadable or unsupported."
            manager.send_progress(video_id, "failed", 2, 6, "Extraction failed: no content could be extracted from the video.")
            return
        else:
            job.extraction_result = extraction_result
            job.current_stage = "extraction_complete"
            job.status = ProcessingStatus.QUEUED

            logger.info("api.extraction_complete", video_id=video_id)
            manager.send_progress(video_id, "extraction_complete", 2, 6, "Step 2/6: Extraction complete ✓")
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.extraction_failed", video_id=video_id, error=repr(exc), exc_info=True)
        manager.send_progress(video_id, "failed", job.step, 6, str(exc))


async def _run_pipeline(
    video_id: str, doc_type: DocType, supplementary_context: str, metadata: DocumentMetadata | None = None,
) -> None:
    """Run the full pipeline in the background with per-stage progress updates."""
    job = _video_jobs.get(video_id)
    if job is None:
        return

    try:
        settings = get_settings()
        mode = ProcessingMode(settings.processing_mode)
        client = create_llm_client(mode, model_override=job.llm_model)
        job.status = ProcessingStatus.PROCESSING

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
                manager.send_progress(
                    video_id, "extracting", 2, 6,
                    f"Step 2/6: Video Indexer processing ({progress})...",
                )

            extraction_result = await extraction_agent.process(
                video_metadata, mode, on_progress=_on_pipeline_extraction_progress
            )

            if not extraction_result.transcript and not extraction_result.scenes and not extraction_result.keyframes:
                raise RuntimeError("Extraction produced no transcript, scenes, or keyframes.")

            job.extraction_result = extraction_result
            manager.send_progress(video_id, "extracting", 2, 6, "Step 2/6: Extraction complete ✓")

        # Step 3/6: Structure
        job.current_stage = "structuring"
        job.step = 3
        manager.send_progress(video_id, "structuring", 3, 6, "Step 3/6: Creating document outline...")

        structure_agent = StructureAgent(client)
        outline = await structure_agent.process(extraction_result, doc_type, supplementary_context, metadata)

        manager.send_progress(video_id, "structuring", 3, 6, "Step 3/6: Outline ready ✓")

        # Step 4/6: Writer
        job.current_stage = "writing"
        job.step = 4
        manager.send_progress(video_id, "writing", 4, 6, "Step 4/6: Writing document...")

        writer_agent = WriterAgent(client)
        document = await writer_agent.process(outline, extraction_result, quality_report=job.quality_report)

        manager.send_progress(video_id, "writing", 4, 6, "Step 4/6: Draft complete ✓")

        # Step 5/6: Editor
        job.current_stage = "editing"
        job.step = 5
        manager.send_progress(video_id, "editing", 5, 6, "Step 5/6: Editing for MS Learn style...")

        editor_agent = EditorAgent(client)
        document = await editor_agent.process(document)

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
            document = await editor_agent.process(document, feedback=feedback)
            evaluation = await evaluate_agent.process(document, extraction_result, quality_report=job.quality_report)

        # Done
        result_doc_id = document.document_id
        _documents[result_doc_id] = document
        _extractions[result_doc_id] = extraction_result

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
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.pipeline_failed", video_id=video_id, error=repr(exc), exc_info=True)
        manager.send_progress(video_id, "failed", job.step, 6, str(exc))


# ---- Video Endpoints ----

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

    return DocumentResponse(
        document_id=doc.document_id,
        doc_type=doc.doc_type,
        markdown_content=doc.markdown_content,
        word_count=doc.word_count,
        revision_number=doc.revision_number,
    )


@router.post("/documents/{document_id}/refine", response_model=GenerateResponse)
async def refine_document(
    document_id: str, request: RefineRequest, background_tasks: BackgroundTasks
) -> GenerateResponse:
    """Iteratively refine a generated document with feedback."""
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

            client = create_llm_client(model_override=llm_model)
            editor = EditorAgent(client)
            refined = await editor.process(doc, feedback=request.feedback)

            if extraction is not None:
                evaluator = EvaluateAgent(client)
                evaluation = await evaluator.process(refined, extraction)
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
        except Exception as exc:
            logger.error("api.refine_failed", doc_id=document_id, error=repr(exc), exc_info=True)
            if video_id:
                manager.send_progress(video_id, "failed", 0, 1, f"Refinement failed: {exc}")

    background_tasks.add_task(_refine)

    return GenerateResponse(
        document_id=document_id,
        status="queued",
        message="Refinement queued.",
    )
