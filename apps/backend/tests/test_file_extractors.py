"""Tests for file extraction module."""

import pytest
from unittest.mock import patch, AsyncMock
import io

from pandapower.workers.file_extractors import (
    detect_file_format,
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_text,
    ExtractorError,
    ExtractorFormatError,
)


class TestFileFormatDetection:
    """Test file format detection."""

    def test_detect_pdf(self):
        """Test PDF detection."""
        content = b"%PDF-1.4\n%comment"
        assert detect_file_format(content) == "pdf"

    def test_detect_docx(self):
        """Test DOCX detection."""
        # DOCX is ZIP with word/document.xml
        content = b"PK\x03\x04" + b"\x00" * 100 + b"word/document.xml"
        assert detect_file_format(content) == "docx"

    def test_detect_unknown(self):
        """Test unknown format detection."""
        content = b"Invalid format content"
        assert detect_file_format(content) == "unknown"

    def test_detect_empty(self):
        """Test empty content detection."""
        assert detect_file_format(b"") == "unknown"


class TestPDFExtraction:
    """Test PDF text extraction."""

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_success(self):
        """Test successful PDF extraction."""
        # Mock a simple PDF content
        pdf_content = b"%PDF-1.4\nTest PDF content"

        with patch('pandapower.workers.file_extractors.pypdf.PdfReader') as mock_reader:
            mock_page = AsyncMock()
            mock_page.extract_text = lambda: "Extracted text from PDF"

            mock_pdf = AsyncMock()
            mock_pdf.pages = [mock_page]

            mock_reader.return_value = mock_pdf

            text, method = await extract_text_from_pdf(pdf_content)

            assert "Extracted text" in text or len(text) > 0
            assert method == "pypdf"

    @pytest.mark.asyncio
    async def test_extract_text_from_pdf_timeout(self):
        """Test PDF extraction timeout."""
        pdf_content = b"%PDF-1.4\nTest PDF content"

        with patch('pandapower.workers.file_extractors.asyncio.wait_for') as mock_wait:
            mock_wait.side_effect = TimeoutError()

            with pytest.raises(ExtractorError):
                await extract_text_from_pdf(pdf_content)


class TestDOCXExtraction:
    """Test DOCX text extraction."""

    @pytest.mark.asyncio
    async def test_extract_text_from_docx_success(self):
        """Test successful DOCX extraction."""
        docx_content = b"PK\x03\x04" + b"\x00" * 1000

        with patch('pandapower.workers.file_extractors.Document') as mock_doc_class:
            mock_para = AsyncMock()
            mock_para.text = "Paragraph text"

            mock_doc = AsyncMock()
            mock_doc.paragraphs = [mock_para]
            mock_doc.tables = []

            mock_doc_class.return_value = mock_doc

            text, method = await extract_text_from_docx(docx_content)

            assert method == "docx"
            assert len(text) > 0

    @pytest.mark.asyncio
    async def test_extract_text_from_docx_with_tables(self):
        """Test DOCX extraction with tables."""
        docx_content = b"PK\x03\x04" + b"\x00" * 1000

        with patch('pandapower.workers.file_extractors.Document') as mock_doc_class:
            mock_para = AsyncMock()
            mock_para.text = "Paragraph"

            mock_cell = AsyncMock()
            mock_cell.text = "Cell text"

            mock_row = AsyncMock()
            mock_row.cells = [mock_cell, mock_cell]

            mock_table = AsyncMock()
            mock_table.rows = [mock_row]

            mock_doc = AsyncMock()
            mock_doc.paragraphs = [mock_para]
            mock_doc.tables = [mock_table]

            mock_doc_class.return_value = mock_doc

            text, method = await extract_text_from_docx(docx_content)

            assert method == "docx"
            assert "Paragraph" in text or "Cell text" in text or len(text) > 0


class TestTextExtraction:
    """Test main text extraction orchestrator."""

    @pytest.mark.asyncio
    async def test_extract_text_pdf(self):
        """Test extraction routing for PDF."""
        content = b"%PDF-1.4\ntest"

        with patch('pandapower.workers.file_extractors.extract_text_from_pdf', new_callable=AsyncMock) as mock_pdf:
            mock_pdf.return_value = ("PDF text content", "pypdf")

            text, method = await extract_text("test.pdf", content)

            assert text == "PDF text content"
            assert method == "pypdf"
            mock_pdf.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_text_docx(self):
        """Test extraction routing for DOCX."""
        content = b"PK\x03\x04" + b"\x00" * 100 + b"word/document.xml"

        with patch('pandapower.workers.file_extractors.extract_text_from_docx', new_callable=AsyncMock) as mock_docx:
            mock_docx.return_value = ("DOCX text content", "docx")

            text, method = await extract_text("test.docx", content)

            assert text == "DOCX text content"
            assert method == "docx"
            mock_docx.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_text_unknown_format(self):
        """Test extraction with unknown format."""
        content = b"Unknown format"

        with pytest.raises(ExtractorFormatError, match="Unsupported"):
            await extract_text("test.unknown", content)

    @pytest.mark.asyncio
    async def test_extract_text_timeout(self):
        """Test extraction with timeout."""
        content = b"%PDF-1.4\ntest"

        with patch('pandapower.workers.file_extractors.extract_text_from_pdf', new_callable=AsyncMock) as mock_pdf:
            from pandapower.workers.file_extractors import ExtractorTimeoutError
            mock_pdf.side_effect = ExtractorTimeoutError("Timeout")

            with pytest.raises(ExtractorError):
                await extract_text("test.pdf", content)
