"""One-off: process the newest placement-agency emails through the new flow.

Pulls recent inbox messages, keeps those from placement sender domains, and runs
EmailIngestWorker._process_message on each (which branches into placement-job
creation). Prints what jobs were created. Safe to re-run (dedup on message id).

Usage:
    cd apps/backend && python3 scripts/test_placement_ingest.py [N]
"""

import asyncio
import sys

sys.path.insert(0, "src")

from pandapower.core.supabase import get_supabase_client  # noqa: E402
from pandapower.integrations.azure import AzureGraphClient  # noqa: E402
from pandapower.integrations.supabase_storage import SupabaseStorageManager  # noqa: E402
from pandapower.workers.email_ingest import EmailIngestWorker  # noqa: E402
from pandapower.workers.placement_jobs import is_placement_sender  # noqa: E402


async def main(limit: int = 3):
    supabase = await get_supabase_client()

    # Azure creds from system_settings (same as /admin/email/run-now)
    resp = await supabase.table("system_settings").select(
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

    azure = AzureGraphClient(
        tenant_id=cfg["tenant_id"],
        client_id=cfg["app_client_id"],
        client_secret=cfg["client_secret"],
        target_mailbox=cfg["target_mailbox"],
    )
    storage = SupabaseStorageManager(supabase)
    worker = EmailIngestWorker(supabase, azure, storage, is_backfill=False)

    # Scan newest 100 inbox messages, keep placement senders.
    listing = await azure.list_messages(page_size=100)
    msgs = listing.get("value", [])
    placement = [
        m for m in msgs
        if is_placement_sender(
            (m.get("from", {}).get("emailAddress", {}) or {}).get("address", ""),
            m.get("bodyPreview", ""),
        )
    ]
    print(f"Found {len(placement)} placement-sender emails in newest {len(msgs)} (processing up to {limit}):\n")

    for m in placement[:limit]:
        sender = m.get("from", {}).get("emailAddress", {}).get("address", "")
        subj = m.get("subject", "")
        print(f"→ {sender} | {subj[:70]}")
        result = await worker._process_message(m, dedup_identity=False)
        print(f"   processed: {result}")

    # Show the resulting placement jobs in the DB
    jobs = await supabase.table("jobs").select(
        "job_number,job_title,job_location,job_security_clearance,"
        "placement_contact_name,placement_contact_phone,assigned_agent_code,status,placement_source_email"
    ).eq("is_placement", True).order("created_at", desc=True).limit(10).execute()

    print("\n=== Placement jobs in DB (newest 10) ===")
    for j in jobs.data or []:
        print(
            f"  {j.get('job_number')}  | {j.get('job_title')}  | מיקום={j.get('job_location')} "
            f"| סיווג={j.get('job_security_clearance')} | איש קשר={j.get('placement_contact_name')} "
            f"({j.get('placement_contact_phone')}) | סוכן={j.get('assigned_agent_code') or '— ממתין לניתוב'} "
            f"| {j.get('status')}"
        )

    await azure.close()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    asyncio.run(main(n))
