"""Phase 6.3: Historical Rejection Data Import from Pipedrive."""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from pandapower.integrations.pipedrive import PipedriveClient
from pandapower.integrations import hub_read

logger = logging.getLogger(__name__)


class PipedriveHistoricalImporter:
    """Imports historical rejection data from Pipedrive deals into PandaPower."""

    REJECTION_KEYWORDS = [
        "reject",
        "declined",
        "not suitable",
        "not fit",
        "unsuitable",
        "fail",
        "cannot proceed",
    ]

    def __init__(self, pipedrive_client: PipedriveClient, supabase_client: Any):
        """Initialize historical importer.

        Args:
            pipedrive_client: PipedriveClient instance
            supabase_client: Supabase client for data storage
        """
        self.pipedrive_client = pipedrive_client
        self.supabase_client = supabase_client

    async def import_all_deal_rejections(
        self, limit: int = 1000
    ) -> dict[str, Any]:
        """Import rejection history from all Pipedrive deals.

        Args:
            limit: Max deals to process (pagination)

        Returns:
            Import results with counts and errors
        """
        results = {
            "deals_processed": 0,
            "rejections_found": 0,
            "rejections_imported": 0,
            "errors": [],
            "duplicates_skipped": 0,
            "deals_skipped_already_imported": 0,
        }

        try:
            # Get all deals from Pipedrive
            deals = await self._fetch_all_deals(limit)

            # Skip deals we've already imported. The per-deal notes fetch
            # (GET /v1/deals/{id}/notes) is the dominant Pipedrive token cost of
            # this job — without this guard every run re-fetches notes for all
            # ~1000 deals. Rejection notes are historical and effectively
            # immutable, so once a deal is processed we never need to hit its
            # notes endpoint again.
            already_processed = await self._already_processed_deal_ids()
            if already_processed:
                before = len(deals)
                deals = [d for d in deals if str(d.get("id")) not in already_processed]
                results["deals_skipped_already_imported"] = before - len(deals)

            for deal in deals:
                deal_id = deal.get("id")
                deal_title = deal.get("title")

                try:
                    # Get rejection notes for this deal
                    rejection_data = await self._extract_deal_rejections(deal_id, deal_title, deal)

                    if rejection_data["rejections"]:
                        results["rejections_found"] += len(rejection_data["rejections"])

                        # Store each rejection in match_state_history
                        for rejection in rejection_data["rejections"]:
                            imported = await self._store_rejection_in_history(deal_id, rejection)
                            if imported:
                                results["rejections_imported"] += 1
                            else:
                                results["duplicates_skipped"] += 1

                    results["deals_processed"] += 1

                except Exception as e:
                    logger.warning(f"Error processing deal {deal_id}: {e}")
                    results["errors"].append(f"Deal {deal_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Error importing historical rejections: {e}")
            results["errors"].append(f"Import failed: {str(e)}")

        logger.info(
            f"Historical import complete: {results['deals_processed']} deals, "
            f"{results['rejections_imported']} rejections imported"
        )

        return results

    async def _already_processed_deal_ids(self) -> set[str]:
        """Return the set of Pipedrive deal IDs already imported.

        Rows are stored in match_state_history with a synthetic match_id of the
        form ``pipedrive_deal_{deal_id}_{note_id}``. We pull those rows once and
        derive the deal IDs so we can skip re-fetching their notes from
        Pipedrive on subsequent runs (the expensive part of this job).
        """
        try:
            res = await (
                self.supabase_client.table("match_state_history")
                .select("match_id")
                .like("match_id", "pipedrive_deal_%")
                .execute()
            )
            deal_ids: set[str] = set()
            for row in (res.data or []):
                mid = row.get("match_id") or ""
                # pipedrive_deal_{deal_id}_{note_id} → middle segment is deal_id
                parts = mid.split("_")
                if len(parts) >= 4:
                    deal_ids.add(parts[2])
            return deal_ids
        except Exception as e:
            # Fail open: if we can't read history, just process everything.
            logger.warning(f"Could not load already-processed deal IDs: {e}")
            return set()

    async def _fetch_all_deals(self, limit: int) -> list[dict]:
        """Fetch all deals from Pipedrive with pagination.

        Args:
            limit: Max deals to fetch

        Returns:
            List of deal objects
        """
        # Hub mirrors ALL deal statuses now → read closed/lost deals from there.
        if hub_read.USE_HUB_READS:
            deals = await hub_read.get_all_deals_from_hub()
            return deals[:limit]

        deals = []
        offset = 0
        page_size = 100

        while len(deals) < limit:
            try:
                response = await self.pipedrive_client._make_request(
                    "GET",
                    "/v1/deals",
                    {"limit": min(page_size, limit - len(deals)), "start": offset},
                )

                if not response.get("success"):
                    break

                page_deals = response.get("data", [])
                if not page_deals:
                    break

                deals.extend(page_deals)
                offset += page_size

                # Check if more pages available
                additional_data = response.get("additional_data", {})
                if not additional_data.get("pagination", {}).get("more_items_in_collection"):
                    break

            except Exception as e:
                logger.warning(f"Error fetching deals at offset {offset}: {e}")
                break

        return deals[:limit]

    async def _extract_deal_rejections(
        self, deal_id: str, deal_title: str, deal_data: dict
    ) -> dict[str, Any]:
        """Extract rejection notes and metadata from a deal.

        Args:
            deal_id: Pipedrive deal ID
            deal_title: Deal title
            deal_data: Full deal object from Pipedrive

        Returns:
            Dict with rejections list and metadata
        """
        result = {
            "deal_id": deal_id,
            "deal_title": deal_title,
            "rejections": [],
        }

        try:
            # Get all notes for this deal — from the Hub mirror when enabled.
            if hub_read.USE_HUB_READS:
                notes = await hub_read.get_deal_notes_from_hub(deal_id)
            else:
                notes_response = await self.pipedrive_client._make_request(
                    "GET", f"/v1/deals/{deal_id}/notes"
                )
                if not notes_response.get("success"):
                    return result
                notes = notes_response.get("data", [])

            # Filter for rejection-related notes
            for note in notes:
                content = note.get("content", "").lower()
                add_time = note.get("add_time")

                # Check if note mentions rejection
                is_rejection = any(keyword in content for keyword in self.REJECTION_KEYWORDS)

                if is_rejection:
                    # Categorize the rejection reason
                    category = self._categorize_rejection(content)

                    result["rejections"].append({
                        "note_id": note.get("id"),
                        "content": note.get("content"),
                        "category": category,
                        "timestamp": add_time,
                        "author_id": note.get("author_id"),
                        "deal_id": deal_id,
                        "deal_title": deal_title,
                    })

        except Exception as e:
            logger.warning(f"Error extracting rejections from deal {deal_id}: {e}")

        return result

    def _categorize_rejection(self, note_content: str) -> str:
        """Categorize a rejection based on note content.

        Args:
            note_content: Note text from Pipedrive

        Returns:
            Rejection category
        """
        content_lower = note_content.lower()

        if "already" in content_lower and "declined" in content_lower:
            return "already_declined"
        elif "conflict" in content_lower or "competitor" in content_lower:
            return "conflict_of_interest"
        elif "clearance" in content_lower:
            return "clearance_mismatch"
        elif "quality" in content_lower or "score" in content_lower:
            return "quality_threshold"
        else:
            return "general_rejection"

    async def _store_rejection_in_history(
        self, deal_id: str, rejection: dict
    ) -> bool:
        """Store a rejection in match_state_history table.

        Args:
            deal_id: Pipedrive deal ID
            rejection: Rejection data dict

        Returns:
            True if successfully stored, False if duplicate
        """
        try:
            # Use the note_id as a unique identifier to avoid duplicates
            # Store in match_state_history with special format
            history_entry = {
                "match_id": f"pipedrive_deal_{deal_id}_{rejection['note_id']}",
                "from_state": "historical_import",
                "to_state": "rejected",
                "details": json.dumps({
                    "rejection_reason": rejection["category"],
                    "rejection_content": rejection["content"],
                    "original_timestamp": rejection["timestamp"],
                    "pipedrive_deal_id": deal_id,
                    "pipedrive_deal_title": rejection["deal_title"],
                    "source": "pipedrive_historical_import",
                }),
            }

            # Try to insert; if exists, skip (duplicate). Must be awaited — the
            # Supabase client here is the AsyncClient; without await the insert
            # coroutine is never executed and nothing is persisted.
            await self.supabase_client.table("match_state_history").insert(
                history_entry
            ).execute()

            return True

        except Exception as e:
            # Check if it's a duplicate (unique constraint)
            if "duplicate" in str(e).lower() or "conflict" in str(e).lower():
                logger.debug(f"Skipping duplicate rejection: {rejection['note_id']}")
                return False
            else:
                logger.error(f"Error storing rejection in history: {e}")
                raise

    async def import_deal_rejection_summary(self, deal_id: str) -> dict[str, Any]:
        """Import rejection summary for a specific deal.

        Args:
            deal_id: Pipedrive deal ID

        Returns:
            Rejection summary
        """
        try:
            response = await self.pipedrive_client._make_request(
                "GET", f"/v1/deals/{deal_id}"
            )

            if not response.get("success"):
                return {"success": False, "error": "Deal not found"}

            deal_data = response.get("data", {})

            rejections = await self._extract_deal_rejections(
                deal_id,
                deal_data.get("title"),
                deal_data,
            )

            return {
                "success": True,
                "deal_id": deal_id,
                "deal_title": deal_data.get("title"),
                "rejection_count": len(rejections["rejections"]),
                "rejections": rejections["rejections"],
            }

        except Exception as e:
            logger.error(f"Error importing deal {deal_id} rejection summary: {e}")
            return {"success": False, "error": str(e)}
