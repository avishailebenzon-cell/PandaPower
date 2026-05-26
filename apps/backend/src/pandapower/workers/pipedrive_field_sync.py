"""Phase 6.2: Pipedrive Field Mapping Validation & Sync."""

import logging
from typing import Any, Optional

from pandapower.core.config import settings
from pandapower.integrations.pipedrive import PipedriveClient

logger = logging.getLogger(__name__)


class PipedriveFieldMapper:
    """Manages Pipedrive custom field mapping and validation."""

    # Expected field mappings (category → pipeline field key)
    REQUIRED_FIELDS = {
        "deal": {
            "rejection_reasons": "Rejection Reasons",  # Custom field for rejection history
            "required_clearance": "Required Clearance",  # Job clearance requirement
        },
        "person": {
            "clearance_level": "Clearance Level",  # Candidate clearance level
            "declining_status": "Declining Status",  # Whether candidate declined
        },
        "organization": {
            "company_category": "Company Category",  # Company type/industry
        },
    }

    def __init__(self, pipedrive_client: PipedriveClient, supabase_client: Any):
        """Initialize field mapper.

        Args:
            pipedrive_client: PipedriveClient instance
            supabase_client: Supabase client for field mapping storage
        """
        self.pipedrive_client = pipedrive_client
        self.supabase_client = supabase_client

    async def validate_all_fields(self) -> dict[str, Any]:
        """Validate that all required custom fields exist in Pipedrive.

        Returns:
            Validation results with found/missing fields
        """
        results = {
            "deal_fields": await self._validate_field_type("deal"),
            "person_fields": await self._validate_field_type("person"),
            "organization_fields": await self._validate_field_type("organization"),
            "all_valid": True,
            "errors": [],
        }

        if not results["deal_fields"]["all_found"]:
            results["all_valid"] = False
            results["errors"].append(
                f"Missing deal fields: {results['deal_fields']['missing']}"
            )

        if not results["person_fields"]["all_found"]:
            results["all_valid"] = False
            results["errors"].append(
                f"Missing person fields: {results['person_fields']['missing']}"
            )

        return results

    async def _validate_field_type(self, field_type: str) -> dict[str, Any]:
        """Validate fields for a specific type (deal, person, organization).

        Args:
            field_type: 'deal', 'person', or 'organization'

        Returns:
            Validation results with found/missing fields
        """
        endpoint = f"/v1/{field_type}Fields"
        expected_fields = self.REQUIRED_FIELDS.get(field_type, {})

        try:
            response = await self.pipedrive_client._make_request("GET", endpoint)

            if not response.get("success"):
                return {
                    "field_type": field_type,
                    "all_found": False,
                    "found": {},
                    "missing": list(expected_fields.keys()),
                    "error": response.get("error"),
                }

            # Map Pipedrive fields by name
            pipedrive_fields = {
                field.get("name"): field for field in response.get("data", [])
            }

            found_fields = {}
            missing_fields = []

            for pd_field_name, field_name in expected_fields.items():
                if field_name in pipedrive_fields:
                    found_fields[pd_field_name] = pipedrive_fields[field_name]
                else:
                    missing_fields.append(pd_field_name)

            return {
                "field_type": field_type,
                "all_found": len(missing_fields) == 0,
                "found": found_fields,
                "missing": missing_fields,
            }

        except Exception as e:
            logger.error(f"Error validating {field_type} fields: {e}")
            return {
                "field_type": field_type,
                "all_found": False,
                "found": {},
                "missing": list(expected_fields.keys()),
                "error": str(e),
            }

    async def sync_field_mappings(self) -> dict[str, Any]:
        """Sync Pipedrive custom fields to database mapping table.

        Returns:
            Sync results with counts of synced fields
        """
        results = {
            "total_synced": 0,
            "by_type": {},
            "errors": [],
        }

        for field_type in ["deal", "person", "organization"]:
            try:
                synced = await self._sync_field_type(field_type)
                results["by_type"][field_type] = synced
                results["total_synced"] += synced
            except Exception as e:
                logger.error(f"Error syncing {field_type} fields: {e}")
                results["errors"].append(f"{field_type}: {str(e)}")

        return results

    async def _sync_field_type(self, field_type: str) -> int:
        """Sync fields for a specific type to database.

        Args:
            field_type: 'deal', 'person', or 'organization'

        Returns:
            Number of fields synced
        """
        endpoint = f"/v1/{field_type}Fields"
        response = await self.pipedrive_client._make_request("GET", endpoint)

        if not response.get("success"):
            return 0

        synced_count = 0
        expected_fields = self.REQUIRED_FIELDS.get(field_type, {})

        for field in response.get("data", []):
            field_name = field.get("name")
            field_key = field.get("key")

            # Check if this is one of our expected fields
            pd_field_name = None
            for expected_name, pipedrive_name in expected_fields.items():
                if pipedrive_name == field_name:
                    pd_field_name = expected_name
                    break

            if pd_field_name:
                # Upsert mapping to database
                try:
                    self.supabase_client.table("pipedrive_field_mappings").upsert(
                        {
                            "field_type": field_type,
                            "field_category": "custom",
                            "pandapower_field_name": pd_field_name,
                            "pipedrive_field_key": field_key,
                            "pipedrive_field_id": field.get("id"),
                            "pipedrive_field_name": field_name,
                            "field_data_type": field.get("field_type"),
                            "is_active": True,
                        },
                        on_conflict="field_type,pandapower_field_name",
                    ).execute()
                    synced_count += 1
                except Exception as e:
                    logger.warning(f"Failed to sync field {field_name}: {e}")

        return synced_count

    async def read_custom_field_value(
        self, entity_type: str, entity_id: str, field_key: str
    ) -> Optional[Any]:
        """Read a custom field value from Pipedrive.

        Args:
            entity_type: 'deal', 'person', or 'organization'
            entity_id: Entity ID in Pipedrive
            field_key: Custom field key

        Returns:
            Field value or None if not found
        """
        endpoint = f"/v1/{entity_type}s/{entity_id}"

        try:
            response = await self.pipedrive_client._make_request("GET", endpoint)

            if response.get("success"):
                entity_data = response.get("data", {})
                return entity_data.get(field_key)

        except Exception as e:
            logger.warning(f"Error reading field {field_key} from {entity_type} {entity_id}: {e}")

        return None

    async def write_custom_field_value(
        self, entity_type: str, entity_id: str, field_key: str, value: Any
    ) -> bool:
        """Write a custom field value to Pipedrive.

        Args:
            entity_type: 'deal', 'person', or 'organization'
            entity_id: Entity ID in Pipedrive
            field_key: Custom field key
            value: Value to write

        Returns:
            True if successful, False otherwise
        """
        endpoint = f"/v1/{entity_type}s/{entity_id}"
        payload = {field_key: value}

        try:
            response = await self.pipedrive_client._make_request(
                "PUT", endpoint, body=payload
            )
            return response.get("success", False)
        except Exception as e:
            logger.error(f"Error writing field {field_key} to {entity_type} {entity_id}: {e}")
            return False
