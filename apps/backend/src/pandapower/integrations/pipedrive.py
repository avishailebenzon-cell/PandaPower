import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds
REQUEST_TIMEOUT = 60.0


class PipedriveClient:
    """Async client for Pipedrive CRM API with retry/backoff logic."""

    def __init__(self, api_token: str, api_domain: str = "https://api.pipedrive.com"):
        """Initialize Pipedrive API client.

        Args:
            api_token: Pipedrive API token
            api_domain: Pipedrive API domain (default: https://api.pipedrive.com)
        """
        self.api_token = api_token
        self.api_domain = api_domain
        self.http_client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        self.rate_limit_remaining = None
        self.rate_limit_reset = None

    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def get_contact_activities(self, contact_id: str) -> list[dict]:
        """Get all activities (interactions) for a contact.

        Args:
            contact_id: Pipedrive person ID

        Returns:
            List of activity objects
        """
        endpoint = f"/v1/persons/{contact_id}/activities"
        response = await self._make_request("GET", endpoint, {"limit": 500})
        return response.get("data", [])

    async def get_contact_notes(self, contact_id: str) -> list[dict]:
        """Get all notes for a contact.

        Args:
            contact_id: Pipedrive person ID

        Returns:
            List of note objects
        """
        endpoint = f"/v1/persons/{contact_id}/notes"
        response = await self._make_request("GET", endpoint, {"limit": 500})
        return response.get("data", [])

    async def get_organization(self, org_id: str) -> dict:
        """Get organization/company details.

        Args:
            org_id: Pipedrive organization ID

        Returns:
            Organization object
        """
        endpoint = f"/v1/organizations/{org_id}"
        response = await self._make_request("GET", endpoint)
        return response.get("data", {})

    async def create_person(
        self, name: str, email: str = None, phone: str = None, custom_fields: dict = None
    ) -> dict:
        """Create a new person (contact) in Pipedrive.

        Args:
            name: Full name of the person
            email: Email address
            phone: Phone number (E.164 format)
            custom_fields: Optional dict of custom field hashes to values

        Returns:
            Created person object with 'id' field
        """
        endpoint = "/v1/persons"
        payload = {"name": name}

        if email:
            payload["email"] = [{"value": email, "primary": True}]

        if phone:
            payload["phone"] = [{"value": phone, "primary": True}]

        if custom_fields:
            payload.update(custom_fields)

        response = await self._make_request("POST", endpoint, body=payload)
        result = response.get("data", {})
        logger.info(f"Created Pipedrive person: {name} (ID: {result.get('id')})")
        return result

    async def write_note_to_deal(self, deal_id: str, note_text: str) -> dict:
        """Write a note to a deal (job posting + candidate match).

        Args:
            deal_id: Pipedrive deal ID
            note_text: Note content

        Returns:
            Created note object
        """
        endpoint = f"/v1/deals/{deal_id}/notes"
        # Add PandaPowerBot prefix to all notes for audit trail
        prefixed_note = f"🐼 [PandaPowerBot] {note_text}"
        payload = {"content": prefixed_note}
        response = await self._make_request("POST", endpoint, body=payload)
        return response.get("data", {})

    async def get_deal_rejections(self, deal_id: str) -> list[dict]:
        """Get past rejection reasons for a deal (candidate-job pairing).

        Args:
            deal_id: Pipedrive deal ID

        Returns:
            List of rejection notes/reasons from PandaPowerBot
        """
        endpoint = f"/v1/deals/{deal_id}/notes"
        response = await self._make_request("GET", endpoint, {"limit": 500})

        # Filter notes that mention rejection AND are from PandaPowerBot
        rejections = []
        for note in response.get("data", []):
            content = note.get("content", "")
            content_lower = content.lower()
            # Only include rejection notes from PandaPowerBot
            if "[pandapowerbot]" in content_lower and ("reject" in content_lower or "declined" in content_lower or "not suitable" in content_lower):
                rejections.append(note)

        return rejections

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        body: dict = None,
    ) -> dict[str, Any]:
        """Make HTTP request to Pipedrive API with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /v1/persons/123)
            params: Query parameters
            body: Request body (for POST/PUT)

        Returns:
            API response as dict
        """
        if params is None:
            params = {}

        # Add API token to params
        params["api_token"] = self.api_token

        url = f"{self.api_domain}{endpoint}"

        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Pipedrive {method} {endpoint} attempt {attempt + 1}/{MAX_RETRIES}")

                kwargs = {"params": params}
                if body:
                    kwargs["json"] = body

                response = await self.http_client.request(
                    method=method,
                    url=url,
                    **kwargs,
                )

                # Track rate limits
                if "X-RateLimit-Remaining" in response.headers:
                    self.rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])
                    self.rate_limit_reset = int(response.headers.get("X-RateLimit-Reset", 0))

                    # If rate limit is low, sleep before next request
                    if self.rate_limit_remaining < 10 and attempt < MAX_RETRIES - 1:
                        logger.warning(f"Rate limit low ({self.rate_limit_remaining} remaining)")

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("retry-after", 60))
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            f"Rate limited by Pipedrive (429), retrying after {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)
                        continue
                    raise Exception(f"Rate limited by Pipedrive after {MAX_RETRIES} attempts")

                # Handle server errors (5xx)
                if response.status_code in (500, 502, 503, 504):
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF * (2**attempt)
                        logger.warning(
                            f"Pipedrive server error {response.status_code}, retrying after {backoff}s"
                        )
                        await asyncio.sleep(backoff)
                        continue

                # Handle timeout (408)
                if response.status_code == 408:
                    if attempt < MAX_RETRIES - 1:
                        backoff = INITIAL_BACKOFF * (2**attempt)
                        logger.warning(f"Pipedrive timeout (408), retrying after {backoff}s")
                        await asyncio.sleep(backoff)
                        continue

                # Handle auth errors (non-retriable)
                if response.status_code == 401:
                    logger.error("Pipedrive authentication error (401)")
                    raise Exception(f"Pipedrive auth error: {response.text}")

                # Handle not found (non-retriable)
                if response.status_code == 404:
                    logger.warning(f"Pipedrive resource not found (404): {endpoint}")
                    # Return empty response for not found
                    return {"success": False, "error": "Resource not found", "data": None}

                # Handle bad request (non-retriable)
                if response.status_code == 400:
                    logger.error(f"Pipedrive bad request (400): {response.text}")
                    raise Exception(f"Pipedrive bad request: {response.text}")

                # Handle other HTTP errors
                if response.status_code >= 400:
                    logger.error(f"Pipedrive HTTP error {response.status_code}: {response.text}")
                    raise Exception(f"Pipedrive error {response.status_code}: {response.text}")

                # Success
                data = response.json()
                logger.debug(f"Pipedrive {method} {endpoint} succeeded")
                return data

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < MAX_RETRIES - 1:
                    backoff = INITIAL_BACKOFF * (2**attempt)
                    logger.warning(f"Pipedrive timeout/connection error, retrying after {backoff}s")
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"Pipedrive connection error after {MAX_RETRIES} attempts: {str(e)}")
                raise Exception(f"Pipedrive connection error: {str(e)}")

            except Exception as e:
                logger.error(f"Pipedrive request failed: {str(e)}")
                raise

        raise Exception("Max retries exceeded")
