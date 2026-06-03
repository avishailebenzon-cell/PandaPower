import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .exceptions import AzureAuthError, AzureGraphError, AzureThrottledError
from .schemas import Attachment, AttachmentMetadata, Email

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
OAUTH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds


class AzureGraphClient:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        target_mailbox: str,
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.target_mailbox = target_mailbox

        self.access_token: str | None = None
        self.token_expires_at: datetime | None = None
        self.http_client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.http_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _get_access_token(self) -> str:
        if self.access_token and self.token_expires_at > datetime.utcnow():
            return self.access_token

        url = OAUTH_TOKEN_URL.format(tenant_id=self.tenant_id)
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }

        try:
            response = await self.http_client.post(url, data=payload)
            response.raise_for_status()
            data = response.json()

            self.access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
            return self.access_token
        except httpx.HTTPError as e:
            logger.error(f"Failed to authenticate with Azure: {e}")
            raise AzureAuthError(f"Authentication failed: {str(e)}") from e

    async def authenticate(self) -> dict[str, Any]:
        token = await self._get_access_token()
        return {"access_token": token, "expires_at": self.token_expires_at}

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> dict[str, Any]:
        token = await self._get_access_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        for attempt in range(MAX_RETRIES):
            try:
                response = await self.http_client.request(method, url, headers=headers, **kwargs)

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise AzureThrottledError(
                        f"Rate limited by Azure Graph: {response.text}", retry_after=retry_after
                    )

                if response.status_code in (503, 504):
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF * (2**attempt)
                        await asyncio.sleep(backoff)
                        continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF * (2**attempt)
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"Graph API error: {e}")
                raise AzureGraphError(f"Graph API error: {e.response.text}") from e
            except httpx.HTTPError as e:
                logger.error(f"Request failed: {e}")
                raise AzureGraphError(f"Request failed: {str(e)}") from e

        raise AzureGraphError("Max retries exceeded")

    async def list_messages(
        self,
        folder: str = "inbox",
        since: datetime | None = None,
        until: datetime | None = None,
        page_size: int = 50,
        next_link: str | None = None,
    ) -> dict[str, Any]:
        """Fetch messages from mailbox.

        Args:
            folder: Mail folder name (default: 'inbox')
            since: Only fetch messages with receivedDateTime >= since (forward scan)
            until: Only fetch messages with receivedDateTime <= until (backward scan)
            page_size: Number of messages per page
            next_link: Continuation token for pagination

        Note: Use `since` for forward chronological scanning. Use `until` for
        backward scanning (older emails first). Do not combine both.
        """
        if next_link:
            response = await self._make_request("GET", next_link)
            return response

        filter_param = []
        if since:
            if since.tzinfo is not None:
                since_utc = since.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                since_utc = since
            iso_date = since_utc.isoformat() + "Z"
            filter_param.append(f"receivedDateTime ge {iso_date}")

        if until:
            if until.tzinfo is not None:
                until_utc = until.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                until_utc = until
            iso_date = until_utc.isoformat() + "Z"
            filter_param.append(f"receivedDateTime le {iso_date}")

        filter_query = " and ".join(filter_param) if filter_param else ""
        url = (
            f"{GRAPH_API_BASE}/users/{self.target_mailbox}/mailFolders/{folder}/messages"
            f"?$select=id,internetMessageId,subject,from,receivedDateTime,bodyPreview"
            f"&$expand=attachments($select=id,name,contentType,size)"
            f"&$top={page_size}"
            f"&$orderBy=receivedDateTime desc"
        )

        if filter_query:
            url += f"&$filter={filter_query}"

        response = await self._make_request("GET", url)
        return response

    async def get_message(self, message_id: str) -> Email:
        url = (
            f"{GRAPH_API_BASE}/users/{self.target_mailbox}/messages/{message_id}"
            f"?$expand=attachments($select=id,name,contentType,size)"
        )

        data = await self._make_request("GET", url)
        return Email(**data)

    async def get_message_raw(self, message_id: str) -> dict[str, Any]:
        """Return the raw Graph message dict (with attachment metadata expanded).

        Shape matches what list_messages yields, so it can be fed directly into
        EmailIngestWorker._process_message for re-ingestion."""
        url = (
            f"{GRAPH_API_BASE}/users/{self.target_mailbox}/messages/{message_id}"
            f"?$select=id,internetMessageId,subject,from,receivedDateTime,bodyPreview,body"
            f"&$expand=attachments($select=id,name,contentType,size)"
        )
        return await self._make_request("GET", url)

    async def list_attachments(self, message_id: str) -> list[AttachmentMetadata]:
        url = (
            f"{GRAPH_API_BASE}/users/{self.target_mailbox}/messages/{message_id}/attachments"
            f"?$select=id,name,contentType,size"
        )

        data = await self._make_request("GET", url)
        attachments = [AttachmentMetadata(**item) for item in data.get("value", [])]
        return attachments

    async def download_attachment(self, message_id: str, attachment_id: str) -> bytes:
        url = (
            f"{GRAPH_API_BASE}/users/{self.target_mailbox}/messages/{message_id}"
            f"/attachments/{attachment_id}/$value"
        )

        response = await self.http_client.get(
            url,
            headers={"Authorization": f"Bearer {await self._get_access_token()}"},
        )
        response.raise_for_status()
        return response.content

    async def send_mail(
        self,
        to: str | list[str],
        subject: str,
        body_html: str,
        importance: str = "normal",
    ) -> None:
        """Send an email FROM the configured target_mailbox.

        Used by AlertService to notify admins about system issues. Requires
        the Azure app registration to have Mail.Send permission.

        Args:
            to: One recipient or a list of recipients
            subject: Email subject
            body_html: HTML body (use <br> for line breaks)
            importance: "low" | "normal" | "high"
        """
        recipients = [to] if isinstance(to, str) else to
        url = f"{GRAPH_API_BASE}/users/{self.target_mailbox}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [
                    {"emailAddress": {"address": addr}} for addr in recipients
                ],
                "importance": importance,
            },
            "saveToSentItems": True,
        }

        token = await self._get_access_token()
        response = await self.http_client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        # sendMail returns 202 Accepted on success
        if response.status_code not in (200, 202):
            raise AzureGraphError(
                f"sendMail failed: HTTP {response.status_code} {response.text[:300]}"
            )
