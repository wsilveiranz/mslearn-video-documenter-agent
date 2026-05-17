"""Document conversion service — converts Word/PDF/PPTX files to Markdown using MarkItDown."""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

# Supported extensions
SUPPORTED_EXTENSIONS: set[str] = {".docx", ".pdf", ".pptx", ".xlsx", ".html", ".csv", ".json", ".xml"}

# Default max file size: 50MB
DEFAULT_MAX_FILE_SIZE_MB = 50

try:
    from markitdown import MarkItDown
except ImportError:
    MarkItDown = None  # type: ignore[assignment,misc]


class ConvertedDocument(BaseModel):
    """Result of converting a document to Markdown."""

    markdown: str = Field(description="Converted Markdown content")
    source_path: str = Field(description="Original file path")
    source_type: str = Field(description="File extension (e.g., '.docx')")
    word_count: int = Field(description="Approximate word count of converted content")
    truncated: bool = Field(default=False, description="Whether content was truncated")


class DocumentConversionError(Exception):
    """Raised when document conversion fails."""


class DocumentConverter:
    """Converts various document formats to Markdown using MarkItDown."""

    def __init__(self, max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB) -> None:
        self._max_file_size_mb = max_file_size_mb

    def convert(self, file_path: str) -> ConvertedDocument:
        """Convert a local file to Markdown.

        Args:
            file_path: Path to the document file.

        Returns:
            ConvertedDocument with the Markdown content.

        Raises:
            DocumentConversionError: If conversion fails.
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file type is unsupported or exceeds size limit.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self._max_file_size_mb:
            raise ValueError(f"File too large: {size_mb:.1f}MB exceeds {self._max_file_size_mb}MB limit")

        if MarkItDown is None:
            raise DocumentConversionError(
                "markitdown package not installed. Install with: pip install 'markitdown[docx,pdf,pptx]'"
            )

        try:
            converter = MarkItDown()
            result = converter.convert(str(path))
            markdown = result.text_content or ""

            word_count = len(markdown.split())

            logger.info(
                "document.converted",
                source=file_path,
                source_type=ext,
                word_count=word_count,
                size_mb=round(size_mb, 2),
            )

            return ConvertedDocument(
                markdown=markdown,
                source_path=str(path),
                source_type=ext,
                word_count=word_count,
            )
        except DocumentConversionError:
            raise
        except Exception as e:
            logger.error("document.conversion_failed", source=file_path, error=str(e))
            raise DocumentConversionError(f"Failed to convert {file_path}: {e}") from e

    def convert_bytes(self, content: bytes, filename: str) -> ConvertedDocument:
        """Convert file content from bytes to Markdown.

        Writes to a temp file and converts. Used for multipart upload API.
        """
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}. Supported: {SUPPORTED_EXTENSIONS}")

        size_mb = len(content) / (1024 * 1024)
        if size_mb > self._max_file_size_mb:
            raise ValueError(f"Content too large: {size_mb:.1f}MB exceeds {self._max_file_size_mb}MB limit")

        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = self.convert(tmp_path)
            # Override source path with original filename
            result.source_path = filename
            return result
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @staticmethod
    def supported_extensions() -> set[str]:
        """Return the set of supported file extensions."""
        return SUPPORTED_EXTENSIONS.copy()
