import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from pandapower.integrations.azure import AzureGraphClient, AzureAuthError, AzureThrottledError


@pytest.fixture
def azure_client():
    return AzureGraphClient(
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret="test-secret",
        target_mailbox="test@example.com",
    )


@pytest.mark.asyncio
async def test_azure_client_authentication(azure_client):
    """Test Azure authentication flow."""
    with patch("pandapower.integrations.azure.client.httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        token = await azure_client._get_access_token()

        assert token == "test-token"
        assert azure_client.access_token == "test-token"
        assert azure_client.token_expires_at is not None


@pytest.mark.asyncio
async def test_azure_client_token_caching(azure_client):
    """Test that tokens are cached and not re-requested."""
    azure_client.access_token = "cached-token"
    azure_client.token_expires_at = datetime.utcnow() + timedelta(hours=1)

    token = await azure_client._get_access_token()

    assert token == "cached-token"


@pytest.mark.asyncio
async def test_azure_client_authentication_failure(azure_client):
    """Test authentication failure handling."""
    with patch("pandapower.integrations.azure.client.httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = Exception("Auth failed")

        with pytest.raises(AzureAuthError):
            await azure_client._get_access_token()


@pytest.mark.asyncio
async def test_list_messages_pagination(azure_client):
    """Test message listing with pagination."""
    with patch.object(azure_client, "_make_request") as mock_request:
        mock_request.return_value = {
            "value": [
                {
                    "id": "msg1",
                    "internetMessageId": "<msg1@example.com>",
                    "subject": "Test",
                    "from": {"emailAddress": {"address": "sender@example.com"}},
                    "receivedDateTime": "2024-01-01T00:00:00Z",
                    "attachments": [],
                }
            ],
            "@odata.nextLink": None,
        }

        result = await azure_client.list_messages(page_size=50)

        assert len(result["value"]) == 1
        assert result["value"][0]["id"] == "msg1"


@pytest.mark.asyncio
async def test_throttle_handling(azure_client):
    """Test handling of API throttling (429)."""
    with patch("pandapower.integrations.azure.client.httpx.AsyncClient.request") as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}
        mock_request.side_effect = mock_response

        with pytest.raises(AzureThrottledError):
            await azure_client._make_request("GET", "http://test")


@pytest.mark.asyncio
async def test_download_attachment(azure_client):
    """Test attachment download."""
    with patch("pandapower.integrations.azure.client.httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.content = b"file-content"
        mock_get.return_value = mock_response

        content = await azure_client.download_attachment("msg1", "att1")

        assert content == b"file-content"
