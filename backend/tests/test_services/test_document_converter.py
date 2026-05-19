"""Tests for the document converter service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.document_converter import (
    ConvertedDocument,
    DocumentConversionError,
    DocumentConverter,
)


class TestDocumentConverter:
    """Tests for DocumentConverter."""

    def test_supported_extensions_returns_copy(self):
        exts = DocumentConverter.supported_extensions()
        assert ".docx" in exts
        assert ".pdf" in exts
        assert ".pptx" in exts
        # Modifying the returned set shouldn't affect the original
        exts.add(".xyz")
        assert ".xyz" not in DocumentConverter.supported_extensions()

    def test_convert_file_not_found(self):
        converter = DocumentConverter()
        with pytest.raises(FileNotFoundError):
            converter.convert("/nonexistent/file.docx")

    def test_convert_unsupported_extension(self, tmp_path):
        unsupported = tmp_path / "file.xyz"
        unsupported.write_text("test")
        converter = DocumentConverter()
        with pytest.raises(ValueError, match="Unsupported file type"):
            converter.convert(str(unsupported))

    def test_convert_file_too_large(self, tmp_path):
        large_file = tmp_path / "large.docx"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB
        converter = DocumentConverter(max_file_size_mb=1)  # 1MB limit
        with pytest.raises(ValueError, match="too large"):
            converter.convert(str(large_file))

    @patch("src.services.document_converter.MarkItDown")
    def test_convert_success(self, mock_markitdown_cls, tmp_path):
        # Create a test file
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake docx content")

        # Mock MarkItDown
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.text_content = "# Test Document\n\nThis is converted content."
        mock_instance.convert.return_value = mock_result
        mock_markitdown_cls.return_value = mock_instance

        converter = DocumentConverter()
        result = converter.convert(str(test_file))

        assert isinstance(result, ConvertedDocument)
        assert result.markdown == "# Test Document\n\nThis is converted content."
        assert result.source_type == ".docx"
        assert result.word_count > 0
        assert not result.truncated

    @patch("src.services.document_converter.MarkItDown")
    def test_convert_bytes_success(self, mock_markitdown_cls):
        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.text_content = "Converted from bytes"
        mock_instance.convert.return_value = mock_result
        mock_markitdown_cls.return_value = mock_instance

        converter = DocumentConverter()
        result = converter.convert_bytes(b"fake content", "document.docx")

        assert result.markdown == "Converted from bytes"
        assert result.source_path == "document.docx"

    def test_convert_bytes_unsupported_type(self):
        converter = DocumentConverter()
        with pytest.raises(ValueError, match="Unsupported"):
            converter.convert_bytes(b"content", "file.xyz")

    def test_convert_bytes_too_large(self):
        converter = DocumentConverter(max_file_size_mb=1)
        with pytest.raises(ValueError, match="too large"):
            converter.convert_bytes(b"x" * (2 * 1024 * 1024), "file.docx")

    @patch("src.services.document_converter.MarkItDown")
    def test_convert_markitdown_error(self, mock_markitdown_cls, tmp_path):
        test_file = tmp_path / "corrupt.docx"
        test_file.write_bytes(b"corrupt data")

        mock_instance = MagicMock()
        mock_instance.convert.side_effect = RuntimeError("Parse error")
        mock_markitdown_cls.return_value = mock_instance

        converter = DocumentConverter()
        with pytest.raises(DocumentConversionError, match="Failed to convert"):
            converter.convert(str(test_file))

    @patch("src.services.document_converter.MarkItDown")
    def test_convert_empty_result(self, mock_markitdown_cls, tmp_path):
        test_file = tmp_path / "empty.docx"
        test_file.write_bytes(b"fake")

        mock_instance = MagicMock()
        mock_result = MagicMock()
        mock_result.text_content = ""
        mock_instance.convert.return_value = mock_result
        mock_markitdown_cls.return_value = mock_instance

        converter = DocumentConverter()
        result = converter.convert(str(test_file))
        assert result.markdown == ""
        assert result.word_count == 0


@pytest.mark.integration
class TestDocumentConverterIntegration:
    """Integration tests using real document files — no mocking.

    These tests verify MarkItDown actually converts documents correctly.
    They catch regressions like #115 where conversion silently fails.
    """

    def test_convert_real_docx(self, sample_docx):
        """Verify .docx conversion produces expected content."""
        converter = DocumentConverter()
        result = converter.convert(str(sample_docx))

        assert result.source_type == ".docx"
        assert result.word_count > 0
        # Verify specific content survived conversion
        assert "Integration Test Document" in result.markdown
        assert "alpha-bravo-charlie" in result.markdown

    def test_convert_real_docx_table(self, sample_docx):
        """Verify table content is extracted from .docx."""
        converter = DocumentConverter()
        result = converter.convert(str(sample_docx))

        # Table cells should appear in output
        assert "Header1" in result.markdown
        assert "CellA" in result.markdown

    def test_convert_real_pdf(self, sample_pdf):
        """Verify .pdf conversion produces expected content."""
        converter = DocumentConverter()
        result = converter.convert(str(sample_pdf))

        assert result.source_type == ".pdf"
        assert result.word_count > 0
        assert "golf-hotel-india" in result.markdown

    def test_convert_real_pptx(self, sample_pptx):
        """Verify .pptx conversion produces expected content."""
        converter = DocumentConverter()
        result = converter.convert(str(sample_pptx))

        assert result.source_type == ".pptx"
        assert result.word_count > 0
        # Verify slide content
        assert "juliet-kilo-lima" in result.markdown or "Presentation Test" in result.markdown

    def test_convert_bytes_real_docx(self, sample_docx):
        """Verify convert_bytes() works with real .docx content."""
        converter = DocumentConverter()
        content = Path(sample_docx).read_bytes()
        result = converter.convert_bytes(content, "test-doc.docx")

        assert result.source_path == "test-doc.docx"
        assert result.word_count > 0
        assert "alpha-bravo-charlie" in result.markdown

    def test_markitdown_dependencies_available(self):
        """Verify all MarkItDown converter dependencies are importable.

        This catches missing dependencies in bundled environments (VSIX/PyInstaller).
        """
        import importlib

        deps = ["mammoth", "pdfminer", "pdfplumber", "pptx"]
        for dep in deps:
            try:
                importlib.import_module(dep)
            except ImportError:
                pytest.fail(f"Required MarkItDown dependency '{dep}' is not importable")
