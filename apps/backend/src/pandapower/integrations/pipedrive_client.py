"""
Pipedrive API Client
Handles authentication and API requests to Pipedrive CRM
"""

import httpx
import asyncio
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


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

    async def get_all_persons(self) -> list:
        """
        Fetch all persons from Pipedrive, handling pagination

        Returns:
            List of all persons
        """
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

    async def get_all_deals(self) -> list:
        """
        Fetch all deals from Pipedrive, handling pagination

        Returns:
            List of all deals
        """
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

    async def get_all_organizations(self) -> list:
        """
        Fetch all organizations from Pipedrive, handling pagination

        Returns:
            List of all organizations
        """
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
