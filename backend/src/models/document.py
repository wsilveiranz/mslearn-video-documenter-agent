"""Data models for document structure and generation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DocType(StrEnum):
    QUICKSTART = "quickstart"
    TUTORIAL = "tutorial"
    HOWTO = "how-to"
    CONCEPT = "concept"
    OVERVIEW = "overview"


class Screenshot(BaseModel):
    """A screenshot selected for inclusion in the document."""

    keyframe_id: str
    source_path: str = Field(description="Path to the original keyframe image")
    output_path: str = Field(default="", description="Path in the output media/ directory")
    alt_text: str = Field(description="Descriptive alt-text for accessibility")
    step_number: int | None = Field(default=None, description="Associated step number")
    caption: str = Field(default="")


class DocumentSection(BaseModel):
    """A section within the document outline."""

    heading: str = Field(description="Section heading (sentence case)")
    level: int = Field(ge=1, le=4, description="Heading level: 1=H1, 2=H2, etc.")
    content_hint: str = Field(default="", description="Brief description of expected content")
    section_type: str = Field(
        default="",
        description="Section type from structure agent (e.g., 'step', 'prerequisites', 'placeholder')",
    )
    is_placeholder: bool = Field(
        default=False,
        description="True if this section is not grounded in video content and needs TODO-marked content",
    )
    source_scenes: list[str] = Field(default_factory=list, description="Scene IDs that map to this section")
    source_transcript_ranges: list[tuple[float, float]] = Field(
        default_factory=list, description="(start, end) timestamp ranges from transcript"
    )
    screenshots: list[Screenshot] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list, description="Step descriptions for procedural sections")
    children: list[DocumentSection] = Field(default_factory=list)


class Frontmatter(BaseModel):
    """MS Learn YAML frontmatter metadata."""

    title: str = Field(description="Article title (43-59 chars recommended)", min_length=1)
    description: str = Field(description="Article description (75-300 chars recommended)", min_length=1)
    author: str = Field(default="")
    ms_author: str = Field(default="", alias="ms.author")
    ms_date: str = Field(default="", alias="ms.date", description="Format: MM/DD/YYYY")
    ms_topic: str = Field(
        default="", alias="ms.topic", description="quickstart|tutorial|how-to|concept-article|overview"
    )
    ms_service: str = Field(default="", alias="ms.service")
    customer_intent: str = Field(default="", description="As a <role>, I want <what> so that <why>")
    ai_usage: str = Field(default="ai-assisted", description="AI disclosure metadata")

    model_config = {"populate_by_name": True}


class DocumentMetadata(BaseModel):
    """User-provided metadata for MS Learn frontmatter fields that cannot be derived from video content."""

    author: str = Field(default="", description="GitHub username of the document author (appears in article byline)")
    ms_author: str = Field(default="", description="Microsoft alias without @microsoft.com (for internal tracking)")
    ms_service: str = Field(default="", description="Azure service slug from MS Learn taxonomy (e.g., azure-openai)")
    customer_intent: str = Field(
        default="",
        description="Reader's goal: 'As a <role>, I want <what> so that <why>'",
    )


class DocumentOutline(BaseModel):
    """Complete document outline produced by the Structure Agent."""

    doc_type: DocType
    frontmatter: Frontmatter
    sections: list[DocumentSection] = Field(default_factory=list)
    screenshots: list[Screenshot] = Field(default_factory=list, description="All screenshots for the document")
    estimated_word_count: int = Field(default=0)


class GeneratedDocument(BaseModel):
    """Final generated document output."""

    document_id: str
    doc_type: DocType
    outline: DocumentOutline
    markdown_content: str = Field(description="Full Markdown text with frontmatter")
    media_files: list[Screenshot] = Field(default_factory=list)
    word_count: int = Field(default=0)
    revision_number: int = Field(default=1)
