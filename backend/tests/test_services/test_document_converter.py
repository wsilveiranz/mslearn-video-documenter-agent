"""Tests for the document converter service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.services.document_converter import (
    SUPPORTED_EXTENSIONS,
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
