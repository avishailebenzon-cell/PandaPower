"""Integration tests for complete CV parsing pipeline."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from pandapower.workers.cv_parse import CVParseWorker


@pytest.fixture
def mock_supabase():
    """Create mock Supabase client with full table interface."""
    client = MagicMock()

    # Mock table query chain
    table_mock = MagicMock()
    select_mock = MagicMock()
    eq_mock = MagicMock()
    limit_mock = MagicMock()
    execute_mock = MagicMock()

    # Set up chain
    client.table.return_value = table_mock
    table_mock.select.return_value = select_mock
    select_mock.eq.return_value = eq_mock
    eq_mock.limit.return_value = limit_mock
    limit_mock.execute.return_value = execute_mock

    return client


@pytest.fixture
def mock_storage():
    """Create mock storage manager."""
    return AsyncMock()


@pytest.fixture
def mock_claude():
    """Create mock Claude client."""
    return AsyncMock()


class TestEndToEndParsing:
    """End-to-end tests for CV parsing."""

    @pytest.mark.asyncio
    async def test_full_pipeline_single_cv(self, mock_supabase, mock_storage, mock_claude):
        """Test complete pipeline: download → extract → parse → store."""

        cv_id = str(uuid.uuid4())
        cv_file = {
            "id": cv_id,
            "storage_path": "cvs/outlook/2026/05/hash123/john_doe.pdf",
            "original_filename": "john_doe.pdf",
        }

        # Mock pending CV query
        pending_query = MagicMock()
        pending_query.data = [cv_file]

        # Setup the table query chain
        table_chain = MagicMock()
        table_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = pending_query
        table_chain.update.return_value.in_.return_value.execute.return_value = None
        table_chain.update.return_value.eq.return_value.execute.return_value = None

        mock_supabase.table.return_value = table_chain

        # Mock file download
        mock_storage.download_file.return_value = b"%PDF-1.4\nSample PDF content"

        # Mock text extraction
        with patch('pandapower.workers.cv_parse.extract_text', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = (
                "John Doe\nEmail: john@example.com\nPhone: +972-54-1234567\nSkills: Python, JavaScript",
                "pypdf"
            )

            # Mock language detection
            with patch('pandapower.workers.cv_parse.detect_language') as mock_lang:
                mock_lang.return_value = "en"

                # Mock Claude API response with realistic data
                mock_claude.parse_cv_structured.return_value = {
                    "extracted_fields": {
                        "name": "John Doe",
                        "email": "john@example.com",
                        "phone": "+972541234567",
                        "skills": ["Python", "JavaScript", "React"],
                        "experience": [
                            {
                                "position": "Senior Engineer",
                                "company": "Tech Corp",
                                "duration": "2020-present"
                            }
                        ],
                        "education": [
                            {
                                "degree": "B.S.",
                                "field": "Computer Science",
                                "institution": "University of California"
                            }
                        ],
                        "clearance_level": "Secret",
                        "geographical_location": "San Francisco, CA",
                        "university_1st_degree": {
                            "name": "University of California",
                            "field": "Computer Science"
                        },
                        "university_2nd_degree": None,
                    },
                    "confidence_scores": {
                        "name": 0.98,
                        "email": 0.97,
                        "phone": 0.95,
                        "skills": 0.92,
                        "experience": 0.88,
                        "education": 0.96,
                        "clearance_level": 0.85,
                        "geographical_location": 0.90,
                        "university_1st_degree": 0.96,
                        "university_2nd_degree": 0.0,
                    },
                    "extraction_notes": "Phone normalized from +972-54-1234567 format",
                    "api_response_tokens": {
                        "prompt_tokens": 1200,
                        "completion_tokens": 450,
                        "total_tokens": 1650,
                    }
                }

                worker = CVParseWorker(mock_supabase, mock_storage, mock_claude)

                result = await worker.parse_pending_cvs()

                # Verify result
                assert result["total_processed"] == 1
                assert result["success"] == 1
                assert result["failed"] == 0
                assert result["tokens_used"] == 1650

                # Verify storage download was called
                mock_storage.download_file.assert_called_with(cv_file["storage_path"])

                # Verify Claude API was called
                mock_claude.parse_cv_structured.assert_called_once()

                # Verify database was updated
                mock_supabase.table.assert_called()

    @pytest.mark.asyncio
    async def test_pipeline_with_hebrew_cv(self, mock_supabase, mock_storage, mock_claude):
        """Test pipeline with Hebrew CV content."""

        cv_id = str(uuid.uuid4())
        cv_file = {
            "id": cv_id,
            "storage_path": "cvs/outlook/2026/05/hash456/anna_nicole.pdf",
            "original_filename": "אנה_ניקול.pdf",
        }

        # Mock pending CV
        pending_query = MagicMock()
        pending_query.data = [cv_file]

        table_chain = MagicMock()
        table_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = pending_query
        table_chain.update.return_value.in_.return_value.execute.return_value = None
        table_chain.update.return_value.eq.return_value.execute.return_value = None
        mock_supabase.table.return_value = table_chain

        # Mock Hebrew CV content
        mock_storage.download_file.return_value = b"%PDF-1.4\n" + "אנה ניקול, אימייל: anna@example.com".encode('utf-8')

        with patch('pandapower.workers.cv_parse.extract_text', new_callable=AsyncMock) as mock_extract:
            hebrew_text = "אנה ניקול\nתעודת זהות הנדסה\nטלפון: +972-54-9876543\nכישורים: Python, Java, Machine Learning"
            mock_extract.return_value = (hebrew_text, "pypdf")

            with patch('pandapower.workers.cv_parse.detect_language') as mock_lang:
                mock_lang.return_value = "he"

                mock_claude.parse_cv_structured.return_value = {
                    "extracted_fields": {
                        "name": "אנה ניקול",
                        "email": "anna@example.com",
                        "phone": "+972549876543",
                        "skills": ["Python", "Java", "Machine Learning"],
                        "experience": [],
                        "education": [
                            {
                                "degree": "B.Sc.",
                                "field": "הנדסה",
                                "institution": "טכניון"
                            }
                        ],
                        "clearance_level": None,
                        "geographical_location": "תל אביב",
                        "university_1st_degree": {
                            "name": "טכניון",
                            "field": "הנדסה"
                        },
                        "university_2nd_degree": None,
                    },
                    "confidence_scores": {
                        "name": 0.96,
                        "email": 0.95,
                        "phone": 0.94,
                        "skills": 0.89,
                        "experience": 0.0,
                        "education": 0.94,
                        "clearance_level": 0.0,
                        "geographical_location": 0.88,
                        "university_1st_degree": 0.95,
                        "university_2nd_degree": 0.0,
                    },
                    "extraction_notes": "Hebrew CV with Israeli phone format",
                    "api_response_tokens": {
                        "prompt_tokens": 1350,
                        "completion_tokens": 480,
                        "total_tokens": 1830,
                    }
                }

                worker = CVParseWorker(mock_supabase, mock_storage, mock_claude)
                result = await worker.parse_pending_cvs()

                assert result["total_processed"] == 1
                assert result["success"] == 1
                assert result["tokens_used"] == 1830

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, mock_supabase, mock_storage, mock_claude):
        """Test error handling throughout pipeline."""

        cv_id = str(uuid.uuid4())
        cv_file = {
            "id": cv_id,
            "storage_path": "cvs/outlook/2026/05/hash789/broken.pdf",
            "original_filename": "broken.pdf",
        }

        # Mock pending CV
        pending_query = MagicMock()
        pending_query.data = [cv_file]

        table_chain = MagicMock()
        table_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = pending_query
        table_chain.update.return_value.in_.return_value.execute.return_value = None
        table_chain.update.return_value.eq.return_value.execute.return_value = None
        mock_supabase.table.return_value = table_chain

        # Mock download error
        mock_storage.download_file.side_effect = Exception("Storage unavailable")

        worker = CVParseWorker(mock_supabase, mock_storage, mock_claude)
        result = await worker.parse_pending_cvs()

        # Should handle gracefully
        assert result["total_processed"] == 1
        assert result["failed"] == 1
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_pipeline_batch_processing(self, mock_supabase, mock_storage, mock_claude):
        """Test batch processing with multiple CVs."""

        cv_ids = [str(uuid.uuid4()) for _ in range(3)]
        cv_files = [
            {
                "id": cv_id,
                "storage_path": f"cvs/outlook/2026/05/{i}/cv{i}.pdf",
                "original_filename": f"cv{i}.pdf",
            }
            for i, cv_id in enumerate(cv_ids)
        ]

        # Mock pending CVs
        pending_query = MagicMock()
        pending_query.data = cv_files

        table_chain = MagicMock()
        table_chain.select.return_value.eq.return_value.limit.return_value.execute.return_value = pending_query
        table_chain.update.return_value.in_.return_value.execute.return_value = None
        table_chain.update.return_value.eq.return_value.execute.return_value = None
        mock_supabase.table.return_value = table_chain

        # Mock successful downloads and extractions
        mock_storage.download_file.return_value = b"%PDF-1.4\nContent"

        with patch('pandapower.workers.cv_parse.extract_text', new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = ("Sample CV text content for testing", "pypdf")

            with patch('pandapower.workers.cv_parse.detect_language') as mock_lang:
                mock_lang.return_value = "en"

                # Mock Claude response
                mock_claude.parse_cv_structured.return_value = {
                    "extracted_fields": {
                        "name": "Test Person",
                        "email": "test@example.com",
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
                        "name": 0.90,
                        "email": 0.88,
                        "phone": 0.0,
                        "skills": 0.0,
                        "experience": 0.0,
                        "education": 0.0,
                        "clearance_level": 0.0,
                        "geographical_location": 0.0,
                        "university_1st_degree": 0.0,
                        "university_2nd_degree": 0.0,
                    },
                    "extraction_notes": "Test extraction",
                    "api_response_tokens": {
                        "prompt_tokens": 1000,
                        "completion_tokens": 300,
                        "total_tokens": 1300,
                    }
                }

                worker = CVParseWorker(mock_supabase, mock_storage, mock_claude, batch_size=3)
                result = await worker.parse_pending_cvs()

                assert result["total_processed"] == 3
                assert result["success"] == 3
                assert result["failed"] == 0
                assert result["tokens_used"] == 3900  # 1300 * 3
