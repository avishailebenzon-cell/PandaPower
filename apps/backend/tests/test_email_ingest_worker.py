import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pandapower.workers.email_ingest import EmailIngestWorker


@pytest.fixture
def email_ingest_worker():
    mock_supabase = AsyncMock()
    mock_azure = AsyncMock()
    mock_storage = AsyncMock()

    return EmailIngestWorker(mock_supabase, mock_azure, mock_storage)


@pytest.mark.asyncio
async def test_is_cv_file():
    """Test CV file detection."""
    assert EmailIngestWorker._is_cv_file("resume.pdf", "application/pdf") is True
    assert EmailIngestWorker._is_cv_file("cv.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document") is True
    assert EmailIngestWorker._is_cv_file("document.pdf", "") is True
    assert EmailIngestWorker._is_cv_file("image.jpg", "image/jpeg") is False
    assert EmailIngestWorker._is_cv_file("archive.zip", "application/zip") is False


@pytest.mark.asyncio
async def test_process_message_no_cv_attachments(email_ingest_worker):
    """Test processing a message with no CV attachments."""
    msg_data = {
        "id": "msg1",
        "subject": "Hello",
        "from": {"emailAddress": {"address": "test@example.com"}},
        "receivedDateTime": "2024-01-01T00:00:00Z",
        "attachments": [{"name": "image.jpg", "contentType": "image/jpeg"}],
    }

    email_ingest_worker.supabase.table = MagicMock(return_value=AsyncMock())
    email_ingest_worker.supabase.table.return_value.upsert.return_value.execute = AsyncMock()
    email_ingest_worker.supabase.table.return_value.update.return_value.eq.return_value.execute = AsyncMock()

    result = await email_ingest_worker._process_message(msg_data)

    assert result["cv_count"] == 0


@pytest.mark.asyncio
async def test_process_attachment_duplicate_detection(email_ingest_worker):
    """Test duplicate file detection."""
    file_content = b"test-file-content"
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Mock duplicate detection
    mock_response = AsyncMock()
    mock_response.data = [{"id": "existing"}]

    email_ingest_worker.supabase.table.return_value.select.return_value.eq.return_value.execute = AsyncMock(
        return_value=mock_response
    )

    email_ingest_worker.azure.download_attachment = AsyncMock(return_value=file_content)

    result = await email_ingest_worker._process_attachment(
        "msg1",
        "sender@example.com",
        "2024-01-01T00:00:00Z",
        {"id": "att1", "name": "resume.pdf", "contentType": "application/pdf"},
    )

    assert result["duplicates"] == 1
    assert result["created"] == 0


@pytest.mark.asyncio
async def test_ingest_recent_emails(email_ingest_worker):
    """Test the main email ingestion flow."""
    mock_response = AsyncMock()
    mock_response.data = [{"setting_value": "null"}]

    email_ingest_worker.supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
        return_value=mock_response
    )

    email_ingest_worker.azure.list_messages = AsyncMock(
        return_value={
            "value": [],
            "@odata.nextLink": None,
        }
    )

    result = await email_ingest_worker.ingest_recent_emails()

    assert result["total_processed"] == 0
    assert "errors" in result
