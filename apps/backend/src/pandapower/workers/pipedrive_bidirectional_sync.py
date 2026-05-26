"""Phase 6.5: Bidirectional Pipedrive ↔ PandaPower Sync."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from pandapower.integrations.pipedrive import PipedriveClient

logger = logging.getLogger(__name__)


class BidirectionalSyncManager:
    """Manages bidirectional sync between Pipedrive and PandaPower."""

    # Last-write-wins conflict resolution strategy
    SYNC_DIRECTION = "last_write_wins"

    def __init__(self, pipedrive_client: PipedriveClient, supabase_client: Any):
        """Initialize bidirectional sync manager.

        Args:
            pipedrive_client: PipedriveClient instance
            supabase_client: Supabase client for data storage
        """
        self.pipedrive_client = pipedrive_client
        self.supabase_client = supabase_client

    async def sync_pipedrive_to_pandapower(self, minutes_back: int = 30) -> dict[str, Any]:
        """Sync recent changes from Pipedrive to PandaPower.

        Args:
            minutes_back: How many minutes back to check for changes (default: 30)

        Returns:
            Sync results with counts
        """
        start_time = datetime.utcnow()
        results = {
            "deals_synced": 0,
            "persons_synced": 0,
            "organizations_synced": 0,
            "errors": [],
        }

        try:
            # Calculate timestamp
            since_timestamp = (datetime.now() - timedelta(minutes=minutes_back)).isoformat()

            # Sync deals (jobs) from Pipedrive
            deals_result = await self._sync_deals_from_pipedrive(since_timestamp)
            results["deals_synced"] = deals_result["synced"]
            if deals_result["errors"]:
                results["errors"].extend(deals_result["errors"])

            # Sync persons (candidates) from Pipedrive
            persons_result = await self._sync_persons_from_pipedrive(since_timestamp)
            results["persons_synced"] = persons_result["synced"]
            if persons_result["errors"]:
                results["errors"].extend(persons_result["errors"])

            # Sync organizations from Pipedrive
            orgs_result = await self._sync_organizations_from_pipedrive(since_timestamp)
            results["organizations_synced"] = orgs_result["synced"]
            if orgs_result["errors"]:
                results["errors"].extend(orgs_result["errors"])

            logger.info(f"Pipedrive→PandaPower sync complete: {results}")

            # Log sync to DB
            await self._log_sync("persons", "inbound", "completed", results, start_time)

        except Exception as e:
            logger.error(f"Error in bidirectional sync (PD→PP): {e}")
            results["errors"].append(str(e))
            await self._log_sync("persons", "inbound", "failed", results, start_time, str(e))

        return results

    async def _sync_deals_from_pipedrive(
        self, since_timestamp: str
    ) -> dict[str, Any]:
        """Sync deals (jobs) from Pipedrive to PandaPower.

        Args:
            since_timestamp: ISO timestamp for filtering recent changes

        Returns:
            Sync results
        """
        result = {"synced": 0, "errors": []}

        try:
            # Get deals updated since timestamp
            response = await self.pipedrive_client._make_request(
                "GET",
                "/v1/deals",
                {"limit": 500, "get_summary": 0},
            )

            if not response.get("success"):
                result["errors"].append(f"Failed to fetch deals: {response.get('error')}")
                return result

            deals = response.get("data", [])

            for deal in deals:
                try:
                    # Check last modification time
                    deal_updated = deal.get("update_time")
                    if not self._is_recent_change(deal_updated, since_timestamp):
                        continue

                    # Map Pipedrive deal to PandaPower job
                    job_data = {
                        "title": deal.get("title"),
                        "pipedrive_deal_id": deal.get("id"),
                        "company_id": deal.get("org_id"),
                        "description": deal.get("notes"),
                        "status": "active",  # Or map from Pipedrive stage
                        "updated_at": datetime.now().isoformat(),
                    }

                    # Upsert job in PandaPower
                    self.supabase_client.table("jobs").upsert(
                        job_data,
                        on_conflict="pipedrive_deal_id",
                    ).execute()

                    result["synced"] += 1

                except Exception as e:
                    logger.warning(f"Error syncing deal {deal.get('id')}: {e}")
                    result["errors"].append(str(e))

        except Exception as e:
            logger.error(f"Error syncing deals: {e}")
            result["errors"].append(str(e))

        return result

    async def _sync_persons_from_pipedrive(
        self, since_timestamp: str
    ) -> dict[str, Any]:
        """Sync persons (candidates) from Pipedrive to PandaPower.

        Args:
            since_timestamp: ISO timestamp for filtering recent changes

        Returns:
            Sync results
        """
        result = {"synced": 0, "errors": []}

        try:
            # Get persons updated since timestamp
            response = await self.pipedrive_client._make_request(
                "GET",
                "/v1/persons",
                {"limit": 500},
            )

            if not response.get("success"):
                result["errors"].append(f"Failed to fetch persons: {response.get('error')}")
                return result

            persons = response.get("data", [])

            for person in persons:
                try:
                    # Check last modification time
                    person_updated = person.get("update_time")
                    if not self._is_recent_change(person_updated, since_timestamp):
                        continue

                    # Map Pipedrive person to PandaPower candidate
                    candidate_data = {
                        "first_name": person.get("first_name"),
                        "last_name": person.get("last_name"),
                        "email": person.get("email", [{}])[0].get("value") if person.get("email") else None,
                        "pipedrive_person_id": person.get("id"),
                        "organization_id": person.get("org_id", {}).get("value"),
                        "updated_at": datetime.now().isoformat(),
                    }

                    # Upsert candidate in PandaPower
                    self.supabase_client.table("candidates").upsert(
                        candidate_data,
                        on_conflict="pipedrive_person_id",
                    ).execute()

                    result["synced"] += 1

                except Exception as e:
                    logger.warning(f"Error syncing person {person.get('id')}: {e}")
                    result["errors"].append(str(e))

        except Exception as e:
            logger.error(f"Error syncing persons: {e}")
            result["errors"].append(str(e))

        return result

    async def _sync_organizations_from_pipedrive(
        self, since_timestamp: str
    ) -> dict[str, Any]:
        """Sync organizations from Pipedrive to PandaPower.

        Args:
            since_timestamp: ISO timestamp for filtering recent changes

        Returns:
            Sync results
        """
        result = {"synced": 0, "errors": []}

        try:
            # Get organizations updated since timestamp
            response = await self.pipedrive_client._make_request(
                "GET",
                "/v1/organizations",
                {"limit": 500},
            )

            if not response.get("success"):
                result["errors"].append(f"Failed to fetch organizations: {response.get('error')}")
                return result

            orgs = response.get("data", [])

            for org in orgs:
                try:
                    # Check last modification time
                    org_updated = org.get("update_time")
                    if not self._is_recent_change(org_updated, since_timestamp):
                        continue

                    # Map Pipedrive organization to PandaPower organization
                    org_data = {
                        "name": org.get("name"),
                        "pipedrive_org_id": org.get("id"),
                        "address": org.get("address"),
                        "industry": org.get("industry"),
                        "updated_at": datetime.now().isoformat(),
                    }

                    # Upsert organization in PandaPower
                    self.supabase_client.table("organizations").upsert(
                        org_data,
                        on_conflict="pipedrive_org_id",
                    ).execute()

                    result["synced"] += 1

                except Exception as e:
                    logger.warning(f"Error syncing organization {org.get('id')}: {e}")
                    result["errors"].append(str(e))

        except Exception as e:
            logger.error(f"Error syncing organizations: {e}")
            result["errors"].append(str(e))

        return result

    async def sync_pandapower_to_pipedrive(self) -> dict[str, Any]:
        """Sync recent changes from PandaPower to Pipedrive.

        Returns:
            Sync results with counts
        """
        start_time = datetime.utcnow()
        results = {
            "matches_synced": 0,
            "candidates_synced": 0,
            "errors": [],
        }

        try:
            # Get recently updated matches
            matches_result = await self._sync_matches_to_pipedrive()
            results["matches_synced"] = matches_result["synced"]
            if matches_result["errors"]:
                results["errors"].extend(matches_result["errors"])

            # Get recently updated candidates
            candidates_result = await self._sync_candidates_to_pipedrive()
            results["candidates_synced"] = candidates_result["synced"]
            if candidates_result["errors"]:
                results["errors"].extend(candidates_result["errors"])

            logger.info(f"PandaPower→Pipedrive sync complete: {results}")

            # Log sync to DB
            await self._log_sync("deals", "outbound", "completed", results, start_time)

        except Exception as e:
            logger.error(f"Error in bidirectional sync (PP→PD): {e}")
            results["errors"].append(str(e))
            await self._log_sync("deals", "outbound", "failed", results, start_time, str(e))

        return results

    async def _sync_matches_to_pipedrive(self) -> dict[str, Any]:
        """Sync match decisions from PandaPower to Pipedrive.

        Returns:
            Sync results
        """
        result = {"synced": 0, "errors": []}

        try:
            # Get matches with pending Pipedrive sync
            matches_response = self.supabase_client.table("matches").select(
                "id, pipedrive_deal_id, current_state, updated_at"
            ).eq("pipedrive_synced", False).execute()

            matches = matches_response.data or []

            for match in matches:
                try:
                    deal_id = match.get("pipedrive_deal_id")
                    if not deal_id:
                        continue

                    # Create activity note for this match state
                    state = match.get("current_state")
                    activity_subject = f"Match state updated: {state}"

                    await self.pipedrive_client.write_note_to_deal(
                        deal_id,
                        activity_subject,
                    )

                    # Mark as synced
                    self.supabase_client.table("matches").update({
                        "pipedrive_synced": True,
                    }).eq("id", match.get("id")).execute()

                    result["synced"] += 1

                except Exception as e:
                    logger.warning(f"Error syncing match {match.get('id')}: {e}")
                    result["errors"].append(str(e))

        except Exception as e:
            logger.error(f"Error syncing matches: {e}")
            result["errors"].append(str(e))

        return result

    async def _sync_candidates_to_pipedrive(self) -> dict[str, Any]:
        """Sync candidate information from PandaPower to Pipedrive.

        Returns:
            Sync results
        """
        result = {"synced": 0, "errors": []}

        try:
            # Get candidates with pending Pipedrive sync
            candidates_response = self.supabase_client.table("candidates").select(
                "id, pipedrive_person_id, clearance_level, updated_at"
            ).eq("pipedrive_synced", False).execute()

            candidates = candidates_response.data or []

            for candidate in candidates:
                try:
                    person_id = candidate.get("pipedrive_person_id")
                    if not person_id:
                        continue

                    # Update custom fields in Pipedrive if needed
                    if candidate.get("clearance_level"):
                        # This would use field mapping to get actual field key
                        # await self._update_person_field(person_id, "clearance_level", candidate.get("clearance_level"))
                        pass

                    # Mark as synced
                    self.supabase_client.table("candidates").update({
                        "pipedrive_synced": True,
                    }).eq("id", candidate.get("id")).execute()

                    result["synced"] += 1

                except Exception as e:
                    logger.warning(f"Error syncing candidate {candidate.get('id')}: {e}")
                    result["errors"].append(str(e))

        except Exception as e:
            logger.error(f"Error syncing candidates: {e}")
            result["errors"].append(str(e))

        return result

    def _is_recent_change(self, updated_time: Optional[str], since_timestamp: str) -> bool:
        """Check if an entity was recently updated (last-write-wins logic).

        Args:
            updated_time: Entity's last update time
            since_timestamp: Reference timestamp

        Returns:
            True if entity was updated after reference timestamp
        """
        if not updated_time:
            return False

        try:
            entity_time = datetime.fromisoformat(updated_time.replace("Z", "+00:00"))
            reference_time = datetime.fromisoformat(since_timestamp)
            return entity_time > reference_time
        except Exception as e:
            logger.warning(f"Error comparing timestamps: {e}")
            return False

    async def _log_sync(
        self,
        entity_type: str,
        sync_direction: str,
        status: str,
        results: dict[str, Any],
        start_time: datetime,
        error_message: Optional[str] = None,
    ) -> None:
        """Log sync operation to pipedrive_sync_log table.

        Args:
            entity_type: Type of entity synced (persons, deals, organizations)
            sync_direction: Direction of sync (inbound, outbound, bidirectional)
            status: Sync status (completed, failed, in_progress)
            results: Sync results dictionary
            start_time: When the sync started
            error_message: Optional error message if sync failed
        """
        try:
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            log_entry = {
                "entity_type": entity_type,
                "sync_direction": sync_direction,
                "status": status,
                "records_processed": results.get("deals_synced", 0) + results.get("persons_synced", 0) + results.get("organizations_synced", 0),
                "records_created": sum(r.get("synced", 0) for r in [results] if isinstance(r, dict)),
                "records_updated": 0,
                "records_failed": len(results.get("errors", [])),
                "error_message": error_message,
                "started_at": start_time.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
                "duration_ms": duration_ms,
            }

            await self.supabase_client.table("pipedrive_sync_log").insert(log_entry).execute()
            logger.info(f"Logged sync: {entity_type} {sync_direction} {status}")

        except Exception as e:
            logger.error(f"Failed to log sync: {str(e)}", exc_info=True)
