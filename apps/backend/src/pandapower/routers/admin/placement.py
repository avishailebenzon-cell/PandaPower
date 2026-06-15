"""On-demand ingestion of placement ("השמה") jobs from recruitment-agency emails.

The scheduled email scan already ingests placement emails automatically. This
router lets a human trigger it immediately over the newest N inbox messages —
handy for testing and for urgent vacancies that shouldn't wait for the next
scan cycle.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.azure import AzureGraphClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager
from pandapower.workers.email_ingest import EmailIngestWorker
from pandapower.workers.placement_jobs import is_placement_sender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/placement-jobs", tags=["placement-jobs"])


class PlacementRunRequest(BaseModel):
    newest: int = 30  # how many of the newest inbox messages to scan


@router.post("/run-now")
async def run_now(
    request: PlacementRunRequest,
    supabase_client=Depends(get_supabase_client),
) -> dict:
    """Scan the newest N inbox messages and ingest any placement-agency vacancies."""
    newest = max(1, min(request.newest, 200))

    # Azure creds from system_settings (same source as the email-ingest run-now).
    resp = await supabase_client.table("system_settings").select(
        "setting_key,setting_value"
    ).in_(
        "setting_key",
        ["azure.tenant_id", "azure.app_client_id", "azure.client_secret", "azure.target_mailbox"],
    ).execute()
    cfg = {}
    for row in resp.data or []:
        key = row["setting_key"].split(".")[-1]
        val = row["setting_value"]
        cfg[key] = val.strip('"') if isinstance(val, str) else val

    if not all(k in cfg for k in ["tenant_id", "app_client_id", "client_secret", "target_mailbox"]):
        raise HTTPException(status_code=400, detail="Azure settings not configured")

    azure = AzureGraphClient(
        tenant_id=cfg["tenant_id"],
        client_id=cfg["app_client_id"],
        client_secret=cfg["client_secret"],
        target_mailbox=cfg["target_mailbox"],
    )
    storage = SupabaseStorageManager(supabase_client)
    worker = EmailIngestWorker(supabase_client, azure, storage, is_backfill=False)

    try:
        listing = await azure.list_messages(page_size=newest)
        messages = listing.get("value", [])
        placement_msgs = [
            m for m in messages
            if is_placement_sender(
                (m.get("from", {}).get("emailAddress", {}) or {}).get("address", ""),
                m.get("bodyPreview", ""),
            )
        ]

        processed = 0
        for m in placement_msgs:
            await worker._process_message(m, dedup_identity=False)
            processed += 1

        # Report the current placement-job count for confirmation.
        jobs = await supabase_client.table("jobs").select(
            "id", count="exact"
        ).eq("is_placement", True).execute()

        return {
            "status": "completed",
            "scanned": len(messages),
            "placement_emails_found": len(placement_msgs),
            "processed": processed,
            "total_placement_jobs": jobs.count if hasattr(jobs, "count") else None,
        }
    except Exception as e:
        logger.error(f"Placement run-now failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await azure.close()
