"""Tests for CV parsing worker."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import json
import uuid

from pandapower.workers.cv_parse import CVParseWorker


@pytest.fixture
def supabase_client():
    """Create mock Supabase client."""
    return MagicMock()


@pytest.fixture
def storage_manager():
    """Create mock storage manager."""
    return AsyncMock()


@pytest.fixture
def claude_client():
    """Create mock Claude client."""
    return AsyncMock()


@pytest.fixture
def cv_parse_worker(supabase_client, storage_manager, claude_client):
    """Create CV parse worker with mocks."""
    return CVParseWorker(
        supabase_client=supabase_client,
        storage_manager=storage_manager,
        claude_client=claude_client,
        batch_size=10,
        parse_timeout=300,
    )


class TestCVParseWorker:
    """Test CVParseWorker class."""

    def test_init(self, cv_parse_worker):
        """Test worker initialization."""
        assert cv_parse_worker.batch_size == 10
        assert cv_parse_worker.parse_timeout == 300

    @pytest.mark.asyncio
    async def test_parse_pending_cvs_no_pending(self, cv_parse_worker, supabase_client):
        """Test parsing with no pending CVs."""
        # Mock empty response
        mock_query = MagicMock()
        mock_query.data = None
        supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_query

        result = await cv_parse_worker.parse_pending_cvs()

        assert result["total_processed"] == 0
        assert result["success"] == 0
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_parse_pending_cvs_with_cvs(self, cv_parse_worker, supabase_client):
        """Test parsing with pending CVs."""
        cv_id = str(uuid.uuid4())

        # Mock pending CVs query
        mock_query = MagicMock()
        mock_query.data = [
            {
                "id": cv_id,
                "storage_path": "cvs/outlook/2026/05/abc123/resume.pdf",
                "original_filename": "resume.pdf",
            }
        ]
        supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_query

        # Mock update for marking as parsing
        update_query = MagicMock()
        update_query.execute.return_value = None
        supabase_client.table.return_value.update.return_value.in_.return_value.execute.return_value = None

        # Mock _parse_single_cv to return success
        with patch.object(cv_parse_worker, '_parse_single_cv', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = {
                "success": True,
                "error": None,
                "tokens_used": 1500,
            }

            result = await cv_parse_worker.parse_pending_cvs()

            assert result["total_processed"] == 1
            assert result["success"] == 1
            assert result["failed"] == 0
            assert result["tokens_used"] == 1500

    @pytest.mark.asyncio
    async def test_parse_single_cv_success(self, cv_parse_worker, storage_manager, claude_client):
        """Test successful single CV parsing."""
        cv_id = str(uuid.uuid4())
        cv_file = {
            "id": cv_id,
            "storage_path": "cvs/outlook/2026/05/abc123/resume.pdf",
            "original_filename": "resume.pdf",
        }

        # Mock file download
        storage_manager.download_file.return_value = b"PDF content"

        # Mock text extraction
        with patch('pandapower.workers.cv_parse.extract_text', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = ("John Doe, john@example.com", "pypdf")

            # Mock language detection
            with patch('pandapower.workers.cv_parse.detect_language') as mock_lang:
                mock_lang.return_value = "en"

                # Mock Claude API response
                claude_client.parse_cv_structured.return_value = {
                    "extracted_fields": {
                        "name": "John Doe",
                        "email": "john@example.com",
                        "phone": None,
                        "skills": [],
                        "experience": [],
                        "education": [],
                        "clearance_level": None,
                        "geographical_location": None,
                        "university_1st_degree": None,
                        "university_2nd_degree": None,
                    },
                    "confidence_scores": {
                        "name": 0.95,
                        "email": 0.98,
                    },
                    "extraction_notes": "Test",
                    "api_response_tokens": {
                        "prompt_tokens": 1000,
                        "completion_tokens": 500,
                        "total_tokens": 1500,
                    }
                }

                # Mock database update
                with patch.object(cv_parse_worker, '_update_cv_record', new_callable=AsyncMock):
                    result = await cv_parse_worker._parse_single_cv(cv_file)

                    assert result["success"] is True
                    assert result["tokens_used"] == 1500
                    assert result["error"] is None

    @pytest.mark.asyncio
    async def test_parse_single_cv_extraction_error(self, cv_parse_worker, storage_manager):
        """Test single CV parsing with extraction error."""
        cv_id = str(uuid.uuid4())
        cv_file = {
            "id": cv_id,
            "storage_path": "cvs/outlook/2026/05/abc123/resume.pdf",
            "original_filename": "resume.pdf",
        }

        storage_manager.download_file.return_value = b"PDF content"

        with patch('pandapower.workers.cv_parse.extract_text', new_callable=AsyncMock) as mock_extract:
            from pandapower.workers.file_extractors import ExtractorError
            mock_extract.side_effect = ExtractorError("Failed to extract")

            with patch.object(cv_parse_worker, '_update_cv_record', new_callable=AsyncMock):
                result = await cv_parse_worker._parse_single_cv(cv_file)

                assert result["success"] is False
                assert "extraction" in result["error"].lower() or "extract" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_detect_language_hebrew(self, cv_parse_worker):
        """Test Hebrew language detection."""
        # Hebrew text with at least 50 characters for reliable detection
        hebrew_text = "שלום עולם, זה טקסט בעברית המכיל מספיק תווים כדי לזהות את השפה בצורה מדויקת וחשוב מאד"

        with patch('pandapower.workers.cv_parse.detect_language') as mock_detect:
            mock_detect.return_value = "he"

            lang = await cv_parse_worker._detect_language(hebrew_text)

            assert lang == "he"

    @pytest.mark.asyncio
    async def test_detect_language_english(self, cv_parse_worker):
        """Test English language detection."""
        english_text = "Hello world, this is a longer English text that has more than fifty characters to ensure detection"

        with patch('pandapower.workers.cv_parse.detect_language') as mock_detect:
            mock_detect.return_value = "en"

            lang = await cv_parse_worker._detect_language(english_text)

            assert lang == "en"

    @pytest.mark.asyncio
    async def test_detect_language_short_text(self, cv_parse_worker):
        """Test language detection with short text."""
        short_text = "Hi"

        lang = await cv_parse_worker._detect_language(short_text)

        assert lang == "en"  # Default to English for short text

    @pytest.mark.asyncio
    async def test_update_cv_record(self, cv_parse_worker, supabase_client):
        """Test CV record update."""
        cv_id = str(uuid.uuid4())
        updates = {
            "parse_status": "success",
            "llm_tokens_used": 1500,
        }

        mock_query = MagicMock()
        mock_query.execute.return_value = None
        supabase_client.table.return_value.update.return_value.eq.return_value.execute.return_value = None

        await cv_parse_worker._update_cv_record(cv_id, updates)

        supabase_client.table.assert_called_with("cv_files")
        supabase_client.table.return_value.update.assert_called_with(updates)

    @pytest.mark.asyncio
    async def test_download_cv_file_success(self, cv_parse_worker, storage_manager):
        """Test successful CV file download."""
        storage_path = "cvs/outlook/2026/05/abc123/resume.pdf"
        file_content = b"PDF content bytes"

        storage_manager.download_file.return_value = file_content

        result = await cv_parse_worker._download_cv_file(storage_path)

        assert result == file_content
        storage_manager.download_file.assert_called_with(storage_path)

    @pytest.mark.asyncio
    async def test_download_cv_file_error(self, cv_parse_worker, storage_manager):
        """Test CV file download error."""
        storage_path = "cvs/outlook/2026/05/abc123/resume.pdf"

        storage_manager.download_file.side_effect = Exception("Download failed")

        with pytest.raises(Exception, match="Download failed"):
            await cv_parse_worker._download_cv_file(storage_path)


class TestCVParseMetrics:
    """Test metrics tracking."""

    @pytest.mark.asyncio
    async def test_metrics_calculation(self, cv_parse_worker, supabase_client):
        """Test metrics are calculated correctly."""
        # Mock 5 CVs: 3 success, 1 failed, 1 error
        mock_query = MagicMock()
        mock_query.data = [
            {"id": str(uuid.uuid4()), "storage_path": f"cvs/{i}", "original_filename": f"cv{i}.pdf"}
            for i in range(5)
        ]
        supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_query

        # Mark as parsing
        supabase_client.table.return_value.update.return_value.in_.return_value.execute.return_value = None

        # Mock parsing results
        parse_results = [
            {"success": True, "error": None, "tokens_used": 1000},
            {"success": True, "error": None, "tokens_used": 1200},
            {"success": True, "error": None, "tokens_used": 1100},
            {"success": False, "error": "Extraction failed", "tokens_used": 0},
            {"success": False, "error": "API error", "tokens_used": 0},
        ]

        with patch.object(cv_parse_worker, '_parse_single_cv', new_callable=AsyncMock) as mock_parse:
            mock_parse.side_effect = parse_results

            result = await cv_parse_worker.parse_pending_cvs()

            assert result["total_processed"] == 5
            assert result["success"] == 3
            assert result["failed"] == 2
            assert result["tokens_used"] == 3300  # 1000 + 1200 + 1100
