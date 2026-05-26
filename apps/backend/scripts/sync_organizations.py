"""Sync organizations from Pipedrive to PandaPower."""

import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.supabase import init_supabase, get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


async def sync_one_org(db: Any, org_data: Dict[str, Any]) -> None:
    """Sync one organization with update-or-insert pattern"""
    try:
        result = await db.table("organizations").update(org_data).eq(
            "pipedrive_org_id", org_data["pipedrive_org_id"]
        ).execute()

        if not result.data or len(result.data) == 0:
            await db.table("organizations").insert(org_data).execute()
    except Exception as e:
        logger.error(f"Failed to sync org {org_data.get('pipedrive_org_id')}: {e}")
        raise


async def main():
    await init_supabase()
    db = await get_supabase_client()

    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    logger.info("Fetching all organizations from Pipedrive...")
    orgs = await pipedrive.get_all_organizations()
    logger.info(f"Got {len(orgs)} organizations")

    synced = 0
    errors = 0

    for org in orgs:
        try:
            org_id = org.get("id")
            name = org.get("name")
            if not org_id or not name:
                continue

            # Try with all columns first; if that fails, fall back to minimal columns.
            org_data = {
                "pipedrive_org_id": org_id,
                "name": name,
            }

            await sync_one_org(db, org_data)
            synced += 1

            if synced % 100 == 0:
                logger.info(f"Synced {synced}/{len(orgs)}...")

        except Exception as e:
            logger.error(f"Error: {e}")
            errors += 1

    await pipedrive.close()

    # Log to sync table
    await db.table("pipedrive_sync_log").insert({
        "entity_type": "organizations",
        "sync_direction": "inbound",
        "status": "completed",
        "total_records": len(orgs),
        "created_count": synced,
        "updated_count": 0,
        "failed_count": errors,
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": datetime.utcnow().isoformat(),
        "details": {"synced": synced, "errors": errors},
    }).execute()

    print(f"\n{'=' * 60}")
    print(f"ORGANIZATIONS SYNC RESULT")
    print(f"{'=' * 60}")
    print(f"  Total fetched: {len(orgs)}")
    print(f"  Synced:        {synced}")
    print(f"  Errors:        {errors}")


if __name__ == "__main__":
    asyncio.run(main())
