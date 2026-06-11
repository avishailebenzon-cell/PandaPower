"""
Thin async client for the Resend email API (https://resend.com/docs/api-reference).

We use Resend instead of Azure Graph for transactional/admin alerts because:
- No mailbox permission grant needed (Azure required Mail.Send + admin consent)
- Faster: single HTTP POST, no OAuth dance per send
- Better deliverability (Resend handles SPF/DKIM via onboarding.resend.dev)
- Trivially testable: one API key, one endpoint

Usage:
    client = ResendClient(api_key="re_...")
    await client.send_email(
        to="admin@example.com",
        subject="Alert",
        html="<p>Something broke</p>",
    )
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


RESEND_API_BASE = "https://api.resend.com"
DEFAULT_FROM = "PandaPower Alerts <onboarding@resend.dev>"
# `onboarding@resend.dev` is Resend's pre-verified sender. Works out of the box
# without domain verification. Replace with a verified custom domain when ready.


class ResendError(Exception):
    """Raised when the Resend API rejects a request."""


class ResendClient:
    def __init__(self, api_key: str, default_from: str = DEFAULT_FROM):
        if not api_key:
            raise ValueError("RESEND_API_KEY is required")
        self.api_key = api_key
        self.default_from = default_from
        self._http = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def send_email(
        self,
        to: str | list[str],
        subject: str,
        html: str,
        from_addr: Optional[str] = None,
        reply_to: Optional[str] = None,
        text: Optional[str] = None,
        attachments: Optional[list[dict]] = None,
    ) -> dict:
        """Send a single email via Resend.

        ``attachments`` (optional) is a list of Resend attachment dicts, e.g.
        ``[{"filename": "cv.pdf", "content": "<base64>"}]`` — used to attach the
        Panda-Tech CV PDF when emailing a candidate to a client.

        Returns the parsed Resend response (includes the message `id`) on success.
        Raises ResendError on any non-2xx response so the caller can surface a
        meaningful failure reason in the UI.
        """
        recipients = [to] if isinstance(to, str) else to
        payload = {
            "from": from_addr or self.default_from,
            "to": recipients,
            "subject": subject,
            "html": html,
        }
        if text:
            payload["text"] = text
        if reply_to:
            payload["reply_to"] = reply_to
        if attachments:
            payload["attachments"] = attachments

        try:
            response = await self._http.post(
                f"{RESEND_API_BASE}/emails",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as e:
            raise ResendError(f"Network error reaching Resend: {e}") from e

        if response.status_code in (200, 202):
            return response.json()

        # Resend returns JSON errors like {"message": "...", "name": "..."}
        try:
            err_body = response.json()
            msg = err_body.get("message") or err_body
        except Exception:
            msg = response.text

        raise ResendError(
            f"Resend API error (HTTP {response.status_code}): {msg}"
        )
