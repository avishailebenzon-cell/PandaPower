"""
Pipedrive API Client
Handles authentication and API requests to Pipedrive CRM
"""

import httpx
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import structlog as _structlog
logger = _structlog.get_logger(__name__)


class PipedriveClient:
    """Async HTTP client for Pipedrive API with retry logic"""

    def __init__(self, api_token: str, api_domain: str = "https://api.pipedrive.com"):
        """
        Initialize Pipedrive API client

        Args:
            api_token: Pipedrive API token
            api_domain: API domain (defaults to https://api.pipedrive.com)
        """
        self.api_token = api_token
        self.api_domain = api_domain.rstrip('/')
        self.client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client"""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=60.0)
        return self.client

    async def _make_request_with_retry(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 3,
        timeout: int = 60,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with retry logic

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., /v1/users/me)
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
            **kwargs: Additional arguments to pass to httpx

        Returns:
            JSON response from API

        Raises:
            Exception: If all retry attempts fail
        """
        url = f"{self.api_domain}{endpoint}"

        # Add API token to params
        params = kwargs.get('params', {})
        params['api_token'] = self.api_token
        kwargs['params'] = params

        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                response = await client.request(
                    method,
                    url,
                    timeout=timeout,
                    **kwargs
                )

                data = response.json() if response.content else {}

                # Check for API errors
                if response.status_code == 401:
                    raise ValueError("Invalid API token (401 Unauthorized)")
                if response.status_code == 404:
                    logger.warning(f"Endpoint not found: {url}")
                    return {}
                if response.status_code >= 500:
                    # Retry on server errors
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"Server error {response.status_code}, retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    raise Exception(f"Server error {response.status_code}: {data}")

                if response.status_code >= 400:
                    raise Exception(f"API error {response.status_code}: {data}")

                return data

            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Request timeout, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                raise Exception("Request timeout after retries")

            except (httpx.RequestError, httpx.HTTPError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error: {e}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                raise Exception(f"Connection failed: {e}")

        raise Exception("All retry attempts failed")

    async def get_user_info(self) -> Dict[str, Any]:
        """
        Get current user information (validates API token)

        Returns:
            User info from Pipedrive
        """
        return await self._make_request_with_retry("GET", "/v1/users/me")

    async def get_persons_paginated(self, limit: int = 500, start: int = 0) -> Dict[str, Any]:
        """
        Fetch persons (contacts) from Pipedrive with pagination

        Args:
            limit: Number of persons per page (max 500)
            start: Pagination offset

        Returns:
            Persons data from Pipedrive
        """
        params = {
            'limit': min(limit, 500),
            'start': start
        }
        return await self._make_request_with_retry("GET", "/v1/persons", params=params)

    async def get_recents_paginated(
        self, since_timestamp: str, items: str, limit: int = 500, start: int = 0
    ) -> Dict[str, Any]:
        """
        Fetch recently-changed entities (delta) via Pipedrive's /v1/recents endpoint.

        Args:
            since_timestamp: UTC timestamp, format "YYYY-MM-DD HH:MM:SS"
            items: entity type filter ("person", "deal", "organization")
            limit: page size (max 500)
            start: pagination offset
        """
        params = {
            "since_timestamp": since_timestamp,
            "items": items,
            "limit": min(limit, 500),
            "start": start,
        }
        return await self._make_request_with_retry("GET", "/v1/recents", params=params)

    async def _get_all_recent(self, items: str, since: datetime) -> list:
        """
        Fetch ALL entities of a given type changed since `since` (delta sync).

        Returns objects in the SAME shape as the corresponding full-fetch method,
        so downstream upsert logic is identical whether the data came from a full
        or delta sync. /v1/recents wraps each object as {item, id, data, timestamp};
        we unwrap and return the inner `data` objects.
        """
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        since_str = since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        all_items: list = []
        start = 0
        limit = 500

        while True:
            response = await self.get_recents_paginated(since_str, items, limit, start)

            if not response.get("success"):
                logger.warning(f"Pipedrive /recents error: {response.get('error')}")
                break

            data = response.get("data", []) or []
            if not data:
                break

            for entry in data:
                if isinstance(entry, dict):
                    obj = entry.get("data")
                    if isinstance(obj, dict):
                        all_items.append(obj)

            additional_data = response.get("additional_data", {})
            if not additional_data.get("pagination", {}).get("more_items_in_collection"):
                break

            start = additional_data.get("pagination", {}).get("next_start", start + limit)

        logger.info(f"Fetched {len(all_items)} recently-changed {items}(s) since {since_str}")
        return all_items

    async def get_all_persons(self, since: Optional[datetime] = None) -> list:
        """
        Fetch persons from Pipedrive, handling pagination.

        If `since` is provided, only persons changed since that timestamp are
        fetched via /v1/recents (delta sync). Otherwise a full fetch is done.

        Returns:
            List of persons
        """
        if since is not None:
            return await self._get_all_recent("person", since)

        all_persons = []
        start = 0
        limit = 500

        while True:
            response = await self.get_persons_paginated(limit=limit, start=start)

            if not response.get("success"):
                logger.warning(f"Pipedrive API error: {response.get('error')}")
                break

            data = response.get("data", [])
            if not data:
                break

            all_persons.extend(data)

            # Check if there are more pages
            additional_data = response.get("additional_data", {})
            if not additional_data.get("pagination", {}).get("more_items_in_collection"):
                break

            start = additional_data.get("pagination", {}).get("next_start", start + limit)

        logger.info(f"Fetched {len(all_persons)} persons from Pipedrive")
        return all_persons

    async def get_deals_paginated(self, limit: int = 500, start: int = 0) -> Dict[str, Any]:
        """
        Fetch deals (job positions) from Pipedrive with pagination

        Args:
            limit: Number of deals per page (max 500)
            start: Pagination offset

        Returns:
            Deals data from Pipedrive
        """
        params = {
            'limit': min(limit, 500),
            'start': start
        }
        return await self._make_request_with_retry("GET", "/v1/deals", params=params)

    async def get_all_deals(self, since: Optional[datetime] = None) -> list:
        """
        Fetch deals from Pipedrive, handling pagination.

        If `since` is provided, only deals changed since that timestamp are
        fetched via /v1/recents (delta sync). Otherwise a full fetch is done.

        Returns:
            List of deals
        """
        if since is not None:
            return await self._get_all_recent("deal", since)

        all_deals = []
        start = 0
        limit = 500

        while True:
            response = await self.get_deals_paginated(limit=limit, start=start)

            if not response.get("success"):
                logger.warning(f"Pipedrive API error: {response.get('error')}")
                break

            data = response.get("data", [])
            if not data:
                break

            all_deals.extend(data)

            # Check if there are more pages
            additional_data = response.get("additional_data", {})
            if not additional_data.get("pagination", {}).get("more_items_in_collection"):
                break

            start = additional_data.get("pagination", {}).get("next_start", start + limit)

        logger.info(f"Fetched {len(all_deals)} deals from Pipedrive")
        return all_deals

    async def get_organizations_paginated(self, limit: int = 500, start: int = 0) -> Dict[str, Any]:
        """
        Fetch organizations from Pipedrive with pagination

        Args:
            limit: Number of organizations per page (max 500)
            start: Pagination offset

        Returns:
            Organizations data from Pipedrive
        """
        params = {
            'limit': min(limit, 500),
            'start': start
        }
        return await self._make_request_with_retry("GET", "/v1/organizations", params=params)

    async def get_all_organizations(self, since: Optional[datetime] = None) -> list:
        """
        Fetch organizations from Pipedrive, handling pagination.

        If `since` is provided, only organizations changed since that timestamp
        are fetched via /v1/recents (delta sync). Otherwise a full fetch is done.

        Returns:
            List of organizations
        """
        if since is not None:
            return await self._get_all_recent("organization", since)

        all_orgs = []
        start = 0
        limit = 500

        while True:
            response = await self.get_organizations_paginated(limit=limit, start=start)

            if not response.get("success"):
                logger.warning(f"Pipedrive API error: {response.get('error')}")
                break

            data = response.get("data", [])
            if not data:
                break

            all_orgs.extend(data)

            additional_data = response.get("additional_data", {})
            if not additional_data.get("pagination", {}).get("more_items_in_collection"):
                break

            start = additional_data.get("pagination", {}).get("next_start", start + limit)

        logger.info(f"Fetched {len(all_orgs)} organizations from Pipedrive")
        return all_orgs

    async def create_person(
        self,
        name: str,
        email: str = None,
        phone: str = None,
        custom_fields: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a new person (contact) in Pipedrive.

        Args:
            name: Full name of the person
            email: Email address
            phone: Phone number
            custom_fields: Optional dict of custom field hashes to values

        Returns:
            API response with created person data (includes 'id' field)
        """
        payload = {
            "name": name,
        }

        if email:
            payload["email"] = [{"value": email, "primary": True}]

        if phone:
            payload["phone"] = [{"value": phone, "primary": True}]

        if custom_fields:
            payload.update(custom_fields)

        response = await self._make_request_with_retry(
            "POST",
            "/v1/persons",
            json=payload,
        )

        if response.get("success"):
            logger.info(
                f"Created Pipedrive person: {name}",
                pipedrive_person_id=response.get("data", {}).get("id"),
            )
            return response.get("data", {})
        else:
            logger.error(
                f"Failed to create Pipedrive person: {response.get('error')}",
            )
            raise Exception(f"Pipedrive API error: {response.get('error')}")

    async def get_pipelines(self) -> list:
        """Fetch all deal pipelines (id + name). Used to map a pipeline name
        like 'גיוס מגזר רפאל' / 'Presale' to its numeric pipeline_id."""
        response = await self._make_request_with_retry("GET", "/v1/pipelines")
        return response.get("data") or []

    async def get_stages(self, pipeline_id: int = None) -> list:
        """Fetch deal stages, optionally filtered to a single pipeline."""
        params = {"pipeline_id": pipeline_id} if pipeline_id else {}
        response = await self._make_request_with_retry(
            "GET", "/v1/stages", params=params
        )
        return response.get("data") or []

    async def search_persons(self, term: str) -> list:
        """Search persons by name/email/phone. Returns list of matched items."""
        if not term:
            return []
        params = {"term": term, "fields": "name", "limit": 20}
        response = await self._make_request_with_retry(
            "GET", "/v1/persons/search", params=params
        )
        items = (response.get("data") or {}).get("items") or []
        return [it.get("item", {}) for it in items if it.get("item")]

    async def search_organizations(self, term: str) -> list:
        """Search organizations by name. Returns list of matched items."""
        if not term:
            return []
        params = {"term": term, "fields": "name", "limit": 20}
        response = await self._make_request_with_retry(
            "GET", "/v1/organizations/search", params=params
        )
        items = (response.get("data") or {}).get("items") or []
        return [it.get("item", {}) for it in items if it.get("item")]

    async def create_organization(
        self, name: str, custom_fields: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create a new organization in Pipedrive. Returns created org data."""
        payload = {"name": name}
        if custom_fields:
            payload.update(custom_fields)
        response = await self._make_request_with_retry(
            "POST", "/v1/organizations", json=payload
        )
        if response.get("success"):
            logger.info(
                f"Created Pipedrive organization: {name}",
                pipedrive_org_id=response.get("data", {}).get("id"),
            )
            return response.get("data", {})
        raise Exception(f"Pipedrive API error (create org): {response.get('error')}")

    async def create_deal(
        self,
        title: str,
        pipeline_id: int = None,
        stage_id: int = None,
        person_id: int = None,
        org_id: int = None,
        custom_fields: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a new deal (job) in Pipedrive.

        Args:
            title: Deal title (built as "#job title# אצל #contact# חברת #org#")
            pipeline_id: Target pipeline id (resolve from pipeline name first)
            stage_id: Optional initial stage id
            person_id: Pipedrive person id (contact)
            org_id: Pipedrive organization id
            custom_fields: dict of custom-field-hash -> value (job fields)

        Returns:
            Created deal data (includes 'id').
        """
        payload: Dict[str, Any] = {"title": title}
        if pipeline_id is not None:
            payload["pipeline_id"] = pipeline_id
        if stage_id is not None:
            payload["stage_id"] = stage_id
        if person_id is not None:
            payload["person_id"] = person_id
        if org_id is not None:
            payload["org_id"] = org_id
        if custom_fields:
            payload.update(custom_fields)

        response = await self._make_request_with_retry(
            "POST", "/v1/deals", json=payload
        )
        if response.get("success"):
            logger.info(
                f"Created Pipedrive deal: {title}",
                pipedrive_deal_id=response.get("data", {}).get("id"),
            )
            return response.get("data", {})
        raise Exception(f"Pipedrive API error (create deal): {response.get('error')}")

    async def create_deal_note(self, deal_id: int, content: str) -> Dict[str, Any]:
        """
        Add a note to a deal.

        Args:
            deal_id: Pipedrive deal id
            content: Note text (supports basic HTML)

        Returns:
            Created note data.
        """
        payload = {"deal_id": deal_id, "content": content}
        response = await self._make_request_with_retry(
            "POST", "/v1/notes", json=payload
        )
        if response.get("success"):
            logger.info("Added note to Pipedrive deal", pipedrive_deal_id=deal_id)
            return response.get("data", {})
        raise Exception(f"Pipedrive API error (create note): {response.get('error')}")

    async def create_person_note(self, person_id: int, content: str) -> Dict[str, Any]:
        """
        Add a note to a person (contact).

        Args:
            person_id: Pipedrive person id
            content: Note text (supports basic HTML)

        Returns:
            Created note data.
        """
        payload = {"person_id": person_id, "content": content}
        response = await self._make_request_with_retry(
            "POST", "/v1/notes", json=payload
        )
        if response.get("success"):
            logger.info("Added note to Pipedrive person", pipedrive_person_id=person_id)
            return response.get("data", {})
        raise Exception(f"Pipedrive API error (create note): {response.get('error')}")

    async def close(self):
        """Close the httpx client"""
        if self.client:
            await self.client.aclose()
            self.client = None

    def __del__(self):
        """Cleanup on object destruction"""
        if self.client:
            try:
                asyncio.get_event_loop().run_until_complete(self.close())
            except:
                pass
