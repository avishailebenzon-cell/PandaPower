"""
Pipedrive Deals Sync Worker
Synchronizes job positions (deals) from Pipedrive to PandaPower database.

Field mappings (Pipedrive custom field -> jobs table column):
- c616325e1187aaa05257f6d4cd9cc3626679b23f  -> job_title
- 9ed8654203d45357d76e8f83ca5a8584f5f8e2fb  -> job_description
- 5198dc3d914cb437bf95133a64809a30f69e3b02  -> job_qualifications
- d04ed525f3ed45fb04383e07f281ad7338a30e4e  -> job_location
- 9997b3547b9295447c03c98343a50f4d8d097361  -> job_security_clearance
- a6a8a84e518fb22fc9920f3e714a2bfaf9f488b5  -> deadline
- 360108d810b89e174c7ca6a3a8222eebfd278bf6  -> priority (enum id -> 1-5)
- org_id (standard)                          -> org_id
- person_id (standard)                       -> person_id
- org_id name lookup                         -> organization_name (ארגון)
- person_id name lookup                      -> contact_person_name (איש קשר)
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient
from pandapower.integrations import hub_read

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipedrive custom field keys
# ---------------------------------------------------------------------------
FIELD_JOB_TITLE = "c616325e1187aaa05257f6d4cd9cc3626679b23f"
FIELD_JOB_DESCRIPTION = "9ed8654203d45357d76e8f83ca5a8584f5f8e2fb"
FIELD_JOB_QUALIFICATIONS = "5198dc3d914cb437bf95133a64809a30f69e3b02"
FIELD_JOB_LOCATION = "d04ed525f3ed45fb04383e07f281ad7338a30e4e"
FIELD_JOB_LOCATION_FORMATTED = "d04ed525f3ed45fb04383e07f281ad7338a30e4e_formatted_address"
FIELD_SECURITY_CLEARANCE = "9997b3547b9295447c03c98343a50f4d8d097361"
FIELD_DEADLINE = "a6a8a84e518fb22fc9920f3e714a2bfaf9f488b5"
FIELD_PRIORITY = "360108d810b89e174c7ca6a3a8222eebfd278bf6"

# Priority option id -> numeric priority (1-5)
PRIORITY_MAPPING = {
    390: 1,  # עדיפות גיוס 1
    391: 2,  # עדיפות גיוס 2
    392: 3,  # עדיפות גיוס 3
    393: 4,  # עדיפות גיוס 4
    394: 5,  # עדיפות גיוס 5
}


def _extract_id(field_value: Any) -> Optional[int]:
    """Extract numeric id from a Pipedrive field that may be int, dict, or None"""
    if field_value is None:
        return None
    if isinstance(field_value, dict):
        v = field_value.get("value") or field_value.get("id")
        return int(v) if v is not None else None
    try:
        return int(field_value)
    except (TypeError, ValueError):
        return None


def _extract_embedded_name(field_value: Any) -> Optional[str]:
    """Pipedrive returns linked person_id/org_id as a dict that includes 'name'.

    Return that embedded name if present, so we can fill contact/org names even
    when the entity isn't in our own synced tables yet.
    """
    if isinstance(field_value, dict):
        name = field_value.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _extract_text(field_value: Any) -> Optional[str]:
    """Extract text safely from a field that may be None / dict / str"""
    if field_value is None:
        return None
    if isinstance(field_value, dict):
        return field_value.get("value") or field_value.get("formatted_address")
    if isinstance(field_value, str):
        return field_value.strip() or None
    return str(field_value)


DEFAULT_PRIORITY = 5  # jobs the recruiter didn't prioritize in Pipedrive -> lowest (5)


def _extract_priority(deal: Dict[str, Any]) -> int:
    """Extract priority - convert Pipedrive option id (390-394) to 1-5.

    Jobs with no priority set (or an unrecognized option) default to 5 (lowest),
    so unprioritized jobs are still visible/sortable instead of being NULL.
    """
    raw = deal.get(FIELD_PRIORITY)
    if raw is None or raw == "":
        return DEFAULT_PRIORITY

    try:
        if isinstance(raw, str):
            first = raw.split(",")[0].strip()
            if not first:
                return DEFAULT_PRIORITY
            option_id = int(first)
        elif isinstance(raw, list):
            if not raw:
                return DEFAULT_PRIORITY
            option_id = int(raw[0])
        else:
            option_id = int(raw)
    except (ValueError, TypeError):
        return DEFAULT_PRIORITY

    return PRIORITY_MAPPING.get(option_id, DEFAULT_PRIORITY)


def _extract_opening_date(deal: Dict[str, Any]) -> Optional[str]:
    """Extract job opening date from deal's add_time field.

    Pipedrive add_time is when the deal was created/opened in Pipedrive,
    representing when the recruitment need was identified.
    """
    add_time = deal.get("add_time")
    if not add_time:
        return None

    if isinstance(add_time, str):
        add_time = add_time.strip()
        # Already ISO (has the 'T' separator) - return as-is.
        if "T" in add_time:
            return add_time
        # Pipedrive's usual format is space-separated: "2026-05-15 04:04:25".
        # Normalize to ISO so it stores cleanly in a timestamptz column.
        if "-" in add_time and ":" in add_time:
            return add_time.replace(" ", "T") + "Z"
        # Otherwise it may be a Unix timestamp string.
        try:
            return datetime.utcfromtimestamp(int(add_time)).isoformat() + "Z"
        except (ValueError, TypeError):
            return None
    elif isinstance(add_time, (int, float)):
        try:
            return datetime.utcfromtimestamp(int(add_time)).isoformat() + "Z"
        except (ValueError, OSError):
            return None

    return None


async def _fetch_contact_name(db: Any, pipedrive_person_id: Optional[int]) -> Optional[str]:
    """Fetch the contact person's full name from the contacts table.

    Args:
        db: Supabase async client
        pipedrive_person_id: The Pipedrive person ID to look up

    Returns:
        The contact's full name, or None if not found
    """
    if not pipedrive_person_id:
        return None

    try:
        contact_response = await db.table("contacts").select("full_name").eq(
            "pipedrive_person_id", pipedrive_person_id
        ).single().execute()

        if contact_response.data:
            return contact_response.data.get("full_name")
    except Exception as e:
        # Contact not found or other error - just log and continue
        logger.debug(f"Could not fetch contact for pipedrive_person_id {pipedrive_person_id}: {e}")

    return None


async def _fetch_organization_name(db: Any, pipedrive_org_id: Optional[int]) -> Optional[str]:
    """Fetch the organization name from the organizations table.

    Args:
        db: Supabase async client
        pipedrive_org_id: The Pipedrive organization ID to look up

    Returns:
        The organization's name, or None if not found
    """
    if not pipedrive_org_id:
        return None

    try:
        # The organizations table is keyed by a deterministic UUID derived from
        # the Pipedrive org id (there is NO pipedrive_org_id column), so look up
        # by that UUID — matching how the rest of the app resolves org names.
        from pandapower.workers.pipedrive_sync import pipedrive_org_id_to_uuid

        org_uuid = pipedrive_org_id_to_uuid(pipedrive_org_id)
        org_response = await db.table("organizations").select("name").eq(
            "id", org_uuid
        ).maybe_single().execute()

        if org_response and org_response.data:
            return org_response.data.get("name")
    except Exception as e:
        # Organization not found or other error - just log and continue
        logger.debug(f"Could not fetch organization for pipedrive_org_id {pipedrive_org_id}: {e}")

    return None


def _extract_deadline(deal: Dict[str, Any]) -> Optional[str]:
    """Extract deadline date from custom field"""
    raw = deal.get(FIELD_DEADLINE)
    if raw is None or raw == "":
        return None
    # Pipedrive returns dates as 'YYYY-MM-DD' strings
    if isinstance(raw, str):
        return raw.strip() or None
    return str(raw)


def _extract_location(deal: Dict[str, Any]) -> Optional[str]:
    """Extract job location - prefer formatted address, fallback to raw field"""
    formatted = deal.get(FIELD_JOB_LOCATION_FORMATTED)
    if formatted and isinstance(formatted, str) and formatted.strip():
        return formatted.strip()

    raw = deal.get(FIELD_JOB_LOCATION)
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return (
            raw.get("formatted_address")
            or raw.get("value")
            or raw.get("address")
            or None
        )
    if isinstance(raw, str):
        return raw.strip() or None
    return None


async def sync_pipedrive_deals(since: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Sync deals (job positions) from Pipedrive to PandaPower jobs table.

    Args:
        since: if provided, only fetch deals changed since this timestamp
            (delta sync via /v1/recents). If None, a full sync is done.
            Upserts are idempotent, so delta never disturbs existing rows.

    Returns:
        Sync summary with counts
    """
    sync_start_time = datetime.utcnow()
    try:
        db = await get_supabase_client()

        pipedrive = PipedriveClient(
            api_token=settings.PIPEDRIVE_API_TOKEN,
            api_domain=settings.PIPEDRIVE_API_DOMAIN,
        )

        sync_mode = "delta" if since is not None else "full"
        logger.info(f"Starting Pipedrive deals sync ({sync_mode})...")
        if hub_read.USE_HUB_READS:
            deals = await hub_read.get_all_deals_from_hub(since=since)
        else:
            deals = await pipedrive.get_all_deals(since=since)
        logger.info(f"Fetched {len(deals)} deals from Pipedrive ({sync_mode})")

        summary = {
            "total_fetched": len(deals),
            "synced": 0,
            "skipped_no_job_title": 0,
            "skipped_wrong_status": 0,
            "errors": [],
        }

        batch_size = 500
        for batch_idx in range(0, len(deals), batch_size):
            batch = deals[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            total_batches = (len(deals) + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} deals)")

            for deal in batch:
                try:
                    # Only sync 'open' or 'active' deals
                    deal_status = deal.get("status")
                    if deal_status is None:
                        summary["skipped_wrong_status"] += 1
                        continue

                    deal_status = (
                        deal_status.lower() if isinstance(deal_status, str) else str(deal_status)
                    )
                    if deal_status not in ["open", "active"]:
                        summary["skipped_wrong_status"] += 1
                        continue

                    # Extract job_title from the custom field ONLY. This field is
                    # the recruiter-filled signal that "this deal is a real job
                    # posting". Deals that leave it blank (sales/consulting/other
                    # pipelines, or deal names that are just a contact note like
                    # "עמוס בטיט - יועץ") are intentionally skipped — falling back
                    # to the deal name surfaced non-job deals into the system.
                    job_title = _extract_text(deal.get(FIELD_JOB_TITLE))
                    if not job_title:
                        summary["skipped_no_job_title"] += 1
                        continue

                    # Extract the Pipedrive person ID and org ID
                    pipedrive_person_id = _extract_id(deal.get("person_id"))
                    pipedrive_org_id = _extract_id(deal.get("org_id"))

                    # Resolve contact/org names. Prefer our synced tables, but fall
                    # back to the name embedded in the deal payload (Pipedrive returns
                    # person_id/org_id as dicts with a 'name'), so the field is filled
                    # even when the org/person isn't in our tables yet.
                    contact_name = (
                        await _fetch_contact_name(db, pipedrive_person_id)
                        or _extract_embedded_name(deal.get("person_id"))
                    )
                    organization_name = (
                        await _fetch_organization_name(db, pipedrive_org_id)
                        or _extract_embedded_name(deal.get("org_id"))
                    )

                    # Build complete deal_data with all field mappings
                    deal_data = {
                        "pipedrive_deal_id": deal.get("id"),
                        "job_title": job_title,
                        "job_description": _extract_text(deal.get(FIELD_JOB_DESCRIPTION)) or "",
                        "job_qualifications": _extract_text(deal.get(FIELD_JOB_QUALIFICATIONS)),
                        "job_location": _extract_location(deal),
                        "job_security_clearance": _extract_text(deal.get(FIELD_SECURITY_CLEARANCE)),
                        "deadline": _extract_deadline(deal),
                        "priority": _extract_priority(deal),
                        "person_id": pipedrive_person_id,
                        "org_id": pipedrive_org_id,
                        "stage_id": _extract_id(deal.get("stage_id")),
                        "status": "open",
                        "contact_person_name": contact_name,  # Contact person name (איש קשר)
                        "organization_name": organization_name,  # Organization name (ארגון)
                        "job_opening_date": _extract_opening_date(deal),  # Job opening date from Pipedrive
                        "pipedrive_last_synced_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                    }

                    # Update-or-insert pattern
                    await _sync_deal(db, deal_data)
                    summary["synced"] += 1

                except Exception as e:
                    logger.error(f"Error syncing deal {deal.get('id')}: {str(e)}")
                    summary["errors"].append({
                        "deal_id": deal.get("id"),
                        "error": str(e),
                    })

            logger.info(
                f"Batch {batch_num}/{total_batches} done. "
                f"Synced: {summary['synced']}, "
                f"Skipped (status): {summary['skipped_wrong_status']}, "
                f"Skipped (no title): {summary['skipped_no_job_title']}, "
                f"Errors: {len(summary['errors'])}"
            )

        # Reconcile deletions: deals removed in Pipedrive (status=deleted) are not
        # returned by /v1/deals at all, so they never reach the loop above and would
        # otherwise stay stuck as 'open' jobs forever. On a FULL sync we have the
        # complete set of live deals, so any 'open' job missing from it was deleted
        # in Pipedrive and should be closed. Skipped on delta sync (partial set).
        if since is None:
            fetched_ids = {deal.get("id") for deal in deals if deal.get("id") is not None}
            summary["deleted_closed"] = await _close_deleted_jobs(db, fetched_ids)

        await pipedrive.close()
        await _log_sync_completion(db, "deals", summary, sync_start_time)

        logger.info(f"Sync completed: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Pipedrive deals sync failed: {str(e)}")
        raise


async def _sync_deal(db: Any, deal_data: Dict[str, Any]) -> None:
    """Sync deal to jobs table using update-or-insert pattern with change detection.

    When a job's specification changes (priority, description, qualifications, etc.):
    1. Detects the change by comparing spec hashes
    2. Invalidates all existing matches
    3. Triggers re-matching for the job
    """
    from pandapower.workers.job_change_detection import compute_job_spec_hash, detect_job_spec_change, extract_changed_fields
    from pandapower.workers.agent_matching import AgentMatchingWorker

    try:
        # First, check if this job already exists.
        # Use maybe_single(): .single() raises PGRST116 ("0 rows") for a brand-new
        # deal not yet in the jobs table, which would abort the insert below.
        existing_response = await db.table("jobs").select("*").eq(
            "pipedrive_deal_id", deal_data["pipedrive_deal_id"]
        ).maybe_single().execute()

        # maybe_single() can return None (not just data=None) on 0 rows, so guard
        # the whole response — otherwise a brand-new deal crashes with
        # "'NoneType' object has no attribute 'data'".
        existing_job = existing_response.data if (existing_response and existing_response.data) else None

        # Add tracking fields to deal_data for Phase 4A integration
        deal_data["pipedrive_last_synced_at"] = datetime.utcnow().isoformat()
        deal_data["last_modified_by"] = "pipedrive_sync"

        # Compute current spec hash
        new_hash = compute_job_spec_hash(deal_data)
        deal_data["job_spec_hash"] = new_hash
        deal_data["spec_last_hash_computed_at"] = datetime.utcnow().isoformat()

        # Update or insert the job
        result = await db.table("jobs").update(deal_data).eq(
            "pipedrive_deal_id", deal_data["pipedrive_deal_id"]
        ).execute()

        if not result.data or len(result.data) == 0:
            # New job - just insert
            await db.table("jobs").insert(deal_data).execute()
            logger.debug(f"Created new job from Pipedrive deal {deal_data['pipedrive_deal_id']}")
            return

        # Job exists - check if spec changed
        if existing_job and existing_job.get("job_spec_hash"):
            old_hash = existing_job.get("job_spec_hash")
            if detect_job_spec_change(old_hash, new_hash):
                logger.info(
                    f"Job spec changed for Pipedrive deal {deal_data['pipedrive_deal_id']}: "
                    f"hash {old_hash[:8]}... -> {new_hash[:8]}..."
                )

                # Extract which fields changed
                changed_fields = extract_changed_fields(existing_job, deal_data)
                if changed_fields:
                    job_id = existing_job.get("id")

                    # Invalidate matches and trigger re-matching
                    try:
                        worker = AgentMatchingWorker(db, None)
                        stats = await worker.invalidate_matches_for_job_change(
                            job_id=job_id,
                            change_reason="specs_changed",
                            previous_values=changed_fields,
                            new_values={k: deal_data.get(k) for k in changed_fields.keys()},
                            invalidated_by="pipedrive_sync"
                        )

                        logger.info(f"Invalidated {stats.get('total_invalidated', 0)} matches for job {job_id}")

                        # Trigger re-matching
                        rematch_result = await worker.trigger_job_rematching(job_id)
                        logger.info(f"Re-matching status for job {job_id}: {rematch_result.get('status')}")

                    except Exception as rematch_error:
                        logger.error(f"Error invalidating matches for job {job_id}: {rematch_error}")
                        # Don't fail the sync if match invalidation fails
                        # The job is already updated, and matches will be cleaned up manually if needed

    except Exception as e:
        logger.error(f"Failed to sync deal {deal_data.get('pipedrive_deal_id')}: {str(e)}", exc_info=True)
        raise


async def _close_deleted_jobs(db: Any, fetched_ids: set) -> int:
    """Mark jobs whose Pipedrive deal no longer exists (deleted) as closed.

    Called on full sync only, where `fetched_ids` is the complete set of live
    Pipedrive deal ids. Any job still flagged 'open' but absent from that set
    had its deal deleted in Pipedrive; we set status='deleted' + is_active=False
    so it stops surfacing to recruiters and matching.

    Returns the number of jobs closed.
    """
    try:
        open_jobs_resp = await db.table("jobs").select(
            "id,pipedrive_deal_id"
        ).eq("status", "open").execute()

        open_jobs = open_jobs_resp.data or []
        stale = [
            j for j in open_jobs
            if j.get("pipedrive_deal_id") not in fetched_ids
        ]

        if not stale:
            return 0

        now = datetime.utcnow().isoformat()
        for job in stale:
            try:
                await db.table("jobs").update({
                    "status": "deleted",
                    "last_modified_by": "pipedrive_sync",
                    "updated_at": now,
                }).eq("id", job["id"]).execute()
            except Exception as e:
                logger.error(
                    f"Failed to close deleted job {job.get('pipedrive_deal_id')}: {e}"
                )

        logger.info(
            f"Closed {len(stale)} job(s) whose Pipedrive deal was deleted: "
            f"{[j.get('pipedrive_deal_id') for j in stale]}"
        )
        return len(stale)

    except Exception as e:
        logger.error(f"Deleted-deal reconciliation failed: {e}")
        return 0


async def _log_sync_completion(
    db: Any, entity_type: str, summary: Dict[str, Any], sync_start_time: datetime
) -> None:
    """Log sync completion to pipedrive_sync_log"""
    try:
        sync_end_time = datetime.utcnow()
        duration_ms = int((sync_end_time - sync_start_time).total_seconds() * 1000)

        await db.table("pipedrive_sync_log").insert({
            "entity_type": entity_type,
            "sync_direction": "inbound",
            "status": "completed",
            "total_records": summary.get("total_fetched", 0),
            "created_count": summary.get("synced", 0),
            "updated_count": 0,
            "failed_count": len(summary.get("errors", [])),
            "started_at": sync_start_time.isoformat(),
            "completed_at": sync_end_time.isoformat(),
            "duration_ms": duration_ms,
            "details": {
                "synced": summary.get("synced", 0),
                "skipped_wrong_status": summary.get("skipped_wrong_status", 0),
                "skipped_no_job_title": summary.get("skipped_no_job_title", 0),
                "deleted_closed": summary.get("deleted_closed", 0),
                "errors": summary.get("errors", []),
            },
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log sync: {str(e)}")
