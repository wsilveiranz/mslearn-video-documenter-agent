"""API route definitions for the Video Documenter backend."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from src.models.document import DocType, GeneratedDocument
from src.models.evaluation import EvaluationReport
from src.models.video import ProcessingStatus, VideoJob

logger = structlog.get_logger()
router = APIRouter(tags=["Video Documenter"])

# ---- In-memory storage (replaced with proper storage in Phase 1) ----
_video_jobs: dict[str, VideoJob] = {}
_documents: dict[str, GeneratedDocument] = {}


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


# ---- Video Endpoints ----

@router.post("/videos/ingest", response_model=IngestResponse)
async def ingest_video(
    file: UploadFile = File(None),
    video_path: str = Form(None),
) -> IngestResponse:
    """Upload or register a video for processing.
    
    Accepts either a file upload or a file path/URL.
    """
    if file is None and video_path is None:
        raise HTTPException(status_code=400, detail="Provide either a file upload or video_path")

    source = video_path or file.filename or "unknown"
    logger.info("api.ingest", source=source)

    # TODO Phase 1: Call IngestionAgent
    # - Validate video format and size
    # - Upload to blob storage (cloud mode)
    # - Create VideoJob record

    video_id = "stub-video-id"
    job = VideoJob(video_id=video_id, status=ProcessingStatus.QUEUED)
    _video_jobs[video_id] = job

    return IngestResponse(
        video_id=video_id,
        status=ProcessingStatus.QUEUED,
        message=f"Video '{source}' queued for processing. This is a stub — full pipeline coming in Phase 1.",
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
async def generate_document(request: GenerateRequest) -> GenerateResponse:
    """Generate an MS Learn document from a processed video."""
    job = _video_jobs.get(request.video_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Video job '{request.video_id}' not found")

    logger.info("api.generate", video_id=request.video_id, doc_type=request.doc_type)

    # TODO Phase 1: Call pipeline (Structure → Writer → Editor → Evaluate)
    doc_id = "stub-doc-id"

    return GenerateResponse(
        document_id=doc_id,
        status="queued",
        message=f"Document generation for '{request.doc_type.value}' queued. Stub — coming in Phase 1.",
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
async def refine_document(document_id: str, request: RefineRequest) -> GenerateResponse:
    """Iteratively refine a generated document with feedback."""
    doc = _documents.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")

    logger.info("api.refine", doc_id=document_id, feedback_length=len(request.feedback))

    # TODO Phase 1: Call EditorAgent with feedback, then re-evaluate
    return GenerateResponse(
        document_id=document_id,
        status="queued",
        message="Refinement queued. Stub — coming in Phase 1.",
    )
