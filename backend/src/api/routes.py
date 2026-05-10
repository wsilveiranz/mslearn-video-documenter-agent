"""API route definitions for the Video Documenter backend."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.agents.editor import EditorAgent
from src.agents.evaluate import EvaluateAgent
from src.agents.ingestion import IngestionAgent
from src.agents.orchestrator import PipelineInput, run_pipeline
from src.api.websocket import manager
from src.config import get_settings
from src.models.document import DocType, GeneratedDocument
from src.models.video import ExtractionResult, ProcessingMode, ProcessingStatus, VideoJob

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


class GenerateResponse(BaseModel):
    document_id: str
    status: str
    message: str


class RefineRequest(BaseModel):
    feedback: str


class StatusResponse(BaseModel):
    video_id: str
    status: ProcessingStatus
    progress_pct: float
    current_stage: str
    document_id: str | None = None


class DocumentResponse(BaseModel):
    document_id: str
    doc_type: DocType
    markdown_content: str
    word_count: int
    revision_number: int


# ---- Health ----

@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "video-documenter"}


# ---- Background task helpers ----

async def _run_ingestion(video_id: str, source: str, *, is_temp_file: bool = False) -> None:
    """Run ingestion in the background and update the video job."""
    job = _video_jobs[video_id]
    try:
        job.status = ProcessingStatus.INGESTING
        job.current_stage = "ingestion"
        job.progress_pct = 10.0
        await manager.send_progress(video_id, "ingestion", 10.0, "Starting ingestion...")

        settings = get_settings()
        mode = ProcessingMode(settings.processing_mode)
        agent = IngestionAgent()
        result = await agent.process(source, mode)

        job.extraction_result = None
        job.status = ProcessingStatus.QUEUED
        job.current_stage = "ingestion_complete"
        job.progress_pct = 20.0
        # Store ingestion output separately — keep job.video_id stable
        job.ingestion_video_id = result.video_id
        job.source_path = result.metadata.source_path

        logger.info("api.ingestion_complete", video_id=video_id, ingestion_id=result.video_id)
        await manager.send_progress(video_id, "ingestion_complete", 20.0, "Ingestion complete")
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.ingestion_failed", video_id=video_id, error=str(exc))
        await manager.send_progress(video_id, "failed", job.progress_pct, str(exc))
    finally:
        if is_temp_file:
            try:
                Path(source).unlink(missing_ok=True)
            except OSError:
                logger.warning("api.temp_cleanup_failed", path=source)


async def _run_pipeline(video_id: str, doc_type: DocType, supplementary_context: str) -> None:
    """Run the full pipeline in the background and update stores."""
    job = _video_jobs.get(video_id)
    if job is None:
        return

    try:
        job.status = ProcessingStatus.EXTRACTING
        job.current_stage = "pipeline"
        job.progress_pct = 30.0
        await manager.send_progress(video_id, "extracting", 30.0, "Extracting video content...")

        settings = get_settings()
        mode = ProcessingMode(settings.processing_mode)

        request = PipelineInput(
            video_source=job.source_path or "",
            doc_type=doc_type,
            processing_mode=mode,
            supplementary_context=supplementary_context,
        )
        workflow_result = await run_pipeline.run(request)
        result = workflow_result.get_outputs()[0]

        _documents[result.document.document_id] = result.document
        _extractions[result.document.document_id] = result.extraction

        job.extraction_result = result.extraction
        job.document_id = result.document.document_id
        job.status = ProcessingStatus.COMPLETED
        job.current_stage = "completed"
        job.progress_pct = 100.0

        logger.info(
            "api.pipeline_complete",
            video_id=video_id,
            doc_id=result.document.document_id,
            passed=result.evaluation.passed,
            score=result.evaluation.scores.overall,
        )
        await manager.send_progress(video_id, "completed", 100.0, "Document generated!")
    except Exception as exc:
        job.status = ProcessingStatus.FAILED
        job.error_message = str(exc)
        logger.error("api.pipeline_failed", video_id=video_id, error=str(exc))
        await manager.send_progress(video_id, "failed", job.progress_pct, str(exc))


# ---- Video Endpoints ----

@router.post("/videos/ingest", response_model=IngestResponse)
async def ingest_video(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = None,
    video_path: str | None = Form(None),
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

    job = VideoJob(video_id=video_id, status=ProcessingStatus.QUEUED)
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

    return StatusResponse(
        video_id=job.video_id,
        status=job.status,
        progress_pct=job.progress_pct,
        current_stage=job.current_stage,
        document_id=job.document_id,
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


# ---- Document Endpoints ----

@router.post("/documents/generate", response_model=GenerateResponse)
async def generate_document(request: GenerateRequest, background_tasks: BackgroundTasks) -> GenerateResponse:
    """Generate an MS Learn document from a processed video."""
    job = _video_jobs.get(request.video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{request.video_id}' not found")

    if job.status == ProcessingStatus.FAILED:
        raise HTTPException(status_code=400, detail=f"Video job '{request.video_id}' has failed: {job.error_message}")

    if job.current_stage != "ingestion_complete":
        raise HTTPException(
            status_code=400,
            detail=f"Video job '{request.video_id}' ingestion is not yet complete (stage: {job.current_stage})",
        )

    logger.info("api.generate", video_id=request.video_id, doc_type=request.doc_type)

    background_tasks.add_task(
        _run_pipeline, request.video_id, request.doc_type, request.supplementary_context
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
        try:
            from src.agents.orchestrator import create_foundry_client

            await manager.send_progress(document_id, "refining", 50.0, "Refining document...")

            client = create_foundry_client()
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
            await manager.send_progress(document_id, "refined", 100.0, "Refinement complete")
        except Exception as exc:
            logger.error("api.refine_failed", doc_id=document_id, error=str(exc))

    background_tasks.add_task(_refine)

    return GenerateResponse(
        document_id=document_id,
        status="queued",
        message="Refinement queued.",
    )
