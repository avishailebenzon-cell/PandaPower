#!/usr/bin/env python3
"""Push Pandi-created contacts that have no Pipedrive person yet.

When Pandi registers a new client while Pipedrive is rate-limited (429) or
otherwise unreachable, the contact is created locally with
``pipedrive_person_id = NULL`` so the conversation can continue (see
agents/pandi/tool_handlers.handle_create_client). The regular pipedrive_sync is
PULL-only (Pipedrive -> DB), so it never pushes these back up.

Run this once the daily Pipedrive budget has reset to backfill the missing
persons. Idempotent: only touches rows with pipedrive_person_id IS NULL, and
sets it (plus pipedrive_last_synced_at) on success. The capped 429 handling in
PipedriveClient means a still-exhausted budget fails fast instead of hanging.

Usage:
    python3 scripts/backfill_pandi_contacts_to_pipedrive.py
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.pipedrive import PipedriveClient
from pandapower.workers.pipedrive_sync import CONTACT_STATUS_FIELD

CONTACT_STATUS_POTENTIAL_CLIENT = 33  # לקוח פוטנציאלי


async def main() -> int:
    if not settings.PIPEDRIVE_API_TOKEN:
        print("PIPEDRIVE_API_TOKEN not configured — nothing to do.")
        return 1

    supabase = await get_supabase_client()

    res = await (
        supabase.table("contacts")
        .select("id, full_name, email, phone, contact_status")
        .is_("pipedrive_person_id", "null")
        .eq("contact_status", "potential_client")
        .execute()
    )
    pending = res.data or []
    print(f"Found {len(pending)} potential-client contacts without a Pipedrive person.")
    if not pending:
        return 0

    client = PipedriveClient(
        settings.PIPEDRIVE_API_TOKEN,
        settings.PIPEDRIVE_API_DOMAIN or "https://api.pipedrive.com",
    )
    pushed = failed = 0
    try:
        for c in pending:
            name = c.get("full_name") or "Unknown"
            try:
                person = await client.create_person(
                    name=name,
                    email=c.get("email"),
                    phone=c.get("phone"),
                    custom_fields={CONTACT_STATUS_FIELD: CONTACT_STATUS_POTENTIAL_CLIENT},
                )
                pid = person.get("id")
                await supabase.table("contacts").update({
                    "pipedrive_person_id": pid,
                    "pipedrive_last_synced_at": datetime.utcnow().isoformat(),
                }).eq("id", c["id"]).execute()
                pushed += 1
                print(f"  ✓ {name} -> Pipedrive person {pid}")
            except Exception as e:
                failed += 1
                print(f"  ✗ {name}: {str(e)[:120]}")
                # If the budget is exhausted again, stop early — the rest will be
                # picked up on the next run.
                if "rate limited" in str(e).lower() or "429" in str(e):
                    print("  Pipedrive budget exhausted — stopping; re-run later.")
                    break
    finally:
        await client.close()

    print(f"Done. pushed={pushed} failed={failed} remaining={len(pending) - pushed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
