"""Data models for video processing and content extraction."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ProcessingMode(str, Enum):
    CLOUD = "cloud"
    LOCAL = "local"


class VideoSourceType(str, Enum):
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


class ProcessingStatus(str, Enum):
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


class VideoJob(BaseModel):
    """Tracks the overall processing state of a video."""

    video_id: str
    status: ProcessingStatus = ProcessingStatus.QUEUED
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0)
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
