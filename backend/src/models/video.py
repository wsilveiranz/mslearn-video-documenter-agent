"""Data models for video processing and content extraction."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ProcessingMode(StrEnum):
    CLOUD = "cloud"
    LOCAL = "local"


class VideoSourceType(StrEnum):
    LOCAL_FILE = "local_file"
    BLOB_URL = "blob_url"
    YOUTUBE = "youtube"
    STREAM = "stream"


class VideoMetadata(BaseModel):
    """Basic metadata about the input video."""

    video_id: str = Field(description="Unique identifier for this video processing job")
    source_path: str = Field(description="Original source path or URL")
    source_type: VideoSourceType
    duration_seconds: float = Field(ge=0, description="Video duration in seconds")
    resolution_width: int = Field(ge=0)
    resolution_height: int = Field(ge=0)
    fps: float = Field(ge=0)
    file_size_bytes: int = Field(ge=0)
    has_audio: bool = Field(default=True, description="Whether the video contains an audio stream")
    blob_url: str | None = Field(default=None, description="Azure Blob Storage URL after upload")


class TranscriptSegment(BaseModel):
    """A timestamped segment of the video transcript."""

    text: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    speaker: str | None = Field(default=None, description="Speaker ID if diarization is available")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BoundingBox(BaseModel):
    """Bounding box for OCR text location."""

    x: float
    y: float
    width: float
    height: float


class OCREntry(BaseModel):
    """On-screen text detected via OCR."""

    text: str
    timestamp_seconds: float = Field(ge=0)
    bounding_box: BoundingBox | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Keyframe(BaseModel):
    """A keyframe extracted from the video."""

    id: str
    timestamp_seconds: float = Field(ge=0)
    image_path: str = Field(description="Local path or blob URL to the keyframe image")
    ocr_text: list[OCREntry] = Field(default_factory=list)
    ui_description: str = Field(default="", description="GPT-4o Vision description of UI state")
    scene_id: str | None = None


class Scene(BaseModel):
    """A detected scene (logical grouping of content)."""

    id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    keyframe_ids: list[str] = Field(default_factory=list)
    description: str = Field(default="", description="Auto-generated scene description")


class Entity(BaseModel):
    """A named entity detected in the video (brands, products, technologies)."""

    name: str
    entity_type: str = Field(description="e.g., brand, product, technology, person")
    mentions: list[float] = Field(default_factory=list, description="Timestamps where entity appears")


class ExtractionResult(BaseModel):
    """Complete extraction output from video analysis."""

    transcript: list[TranscriptSegment] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    keyframes: list[Keyframe] = Field(default_factory=list)
    ocr_entries: list[OCREntry] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    video_metadata: VideoMetadata
    processing_mode: ProcessingMode


class IngestionResult(BaseModel):
    """Output from the Ingestion Agent."""

    video_id: str
    blob_url: str | None = None
    metadata: VideoMetadata
    processing_mode: ProcessingMode


class ProcessingStatus(StrEnum):
    QUEUED = "queued"
    INGESTING = "ingesting"
    PROCESSING = "processing"
    EXTRACTING = "extracting"
    STRUCTURING = "structuring"
    WRITING = "writing"
    EDITING = "editing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class DataQualityReport(BaseModel):
    """LLM-generated assessment of extraction data quality and grounding potential."""

    quality_level: Literal["rich", "adequate", "thin", "minimal"]
    transcript_assessment: str = Field(description="LLM assessment of transcript quality and coherence")
    visual_assessment: str = Field(description="LLM assessment of visual evidence sufficiency")
    coverage_gaps: list[str] = Field(default_factory=list, description="Areas with no extraction evidence")
    warnings: list[str] = Field(default_factory=list, description="User-facing warnings about data quality")
    recommendations: list[str] = Field(default_factory=list, description="Actionable suggestions to improve quality")
    grounding_confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence that extraction data can ground a full document",
    )
    raw_metrics: dict = Field(default_factory=dict, description="Deterministic counts for reference")


class VideoJob(BaseModel):
    """Tracks the overall processing state of a video."""

    video_id: str
    status: ProcessingStatus = ProcessingStatus.QUEUED
    step: int = Field(default=0, description="Current step number (0 = not started, 1-6 = pipeline steps)")
    total_steps: int = Field(default=6, description="Total number of pipeline steps")
    current_stage: str = ""
    error_message: str | None = None
    extraction_result: ExtractionResult | None = None
    source_path: str | None = Field(default=None, description="Staged file path after ingestion")
    video_metadata: VideoMetadata | None = Field(
        default=None, description="Cached metadata from ingestion to avoid re-probing"
    )
    ingestion_video_id: str | None = Field(
        default=None, description="Video ID assigned by the ingestion agent"
    )
    document_id: str | None = Field(
        default=None, description="Document ID populated when pipeline completes"
    )
    quality_report: DataQualityReport | None = Field(
        default=None, description="LLM-generated quality assessment of extraction data"
    )
