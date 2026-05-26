"""
Sync organizations from Pipedrive and update all contact-organization
and job-contact/organization relationships.

Strategy (since we can't ALTER the existing 'organizations' table to add
pipedrive_org_id, we generate a deterministic UUID v5 from pipedrive_org_id):

1. Fetch all organizations from Pipedrive
2. Upsert each org into the organizations table with:
   - id = uuid5(ORG_NAMESPACE, str(pipedrive_org_id))
   - name = org name from Pipedrive
3. For each person from Pipedrive:
   - update contacts.pipedrive_org_id (BIGINT, raw Pipedrive id)
   - update contacts.organization_id (UUID, matching organizations.id)
4. Jobs already have org_id (BIGINT) and person_id (BIGINT) populated by the
   deals sync - this script verifies they're set.
"""

import asyncio
import logging
import sys
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.supabase import init_supabase, get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Fixed namespace for deterministic UUIDs from Pipedrive org ids
ORG_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def pipedrive_org_id_to_uuid(pipedrive_org_id: int) -> str:
    """Generate a deterministic UUID for an organization based on its Pipedrive id"""
    return str(uuid.uuid5(ORG_NAMESPACE, f"pipedrive_org:{pipedrive_org_id}"))


def extract_person_org_id(person: Dict[str, Any]) -> Optional[int]:
    """Extract organization id from a Pipedrive person object"""
    org_id = person.get("org_id")
    if org_id is None:
        return None
    if isinstance(org_id, dict):
        v = org_id.get("value") or org_id.get("id")
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    try:
        return int(org_id)
    except (TypeError, ValueError):
        return None


async def sync_organizations(db: Any, pipedrive: PipedriveClient) -> Dict[int, str]:
    """
    Sync all organizations from Pipedrive.
    Returns mapping: pipedrive_org_id -> our_uuid
    """
    logger.info("Fetching all organizations from Pipedrive...")
    orgs = await pipedrive.get_all_organizations()
    logger.info(f"Got {len(orgs)} organizations from Pipedrive")

    # Build pipedrive_org_id -> uuid mapping
    pipedrive_to_uuid: Dict[int, str] = {}
    org_records: List[Dict[str, Any]] = []

    for org in orgs:
        pd_id = org.get("id")
        name = org.get("name")
        if not pd_id or not name:
            continue

        org_uuid = pipedrive_org_id_to_uuid(pd_id)
        pipedrive_to_uuid[int(pd_id)] = org_uuid
        org_records.append({
            "id": org_uuid,
            "name": name,
        })

    logger.info(f"Prepared {len(org_records)} org records")

    # Wipe ALL existing rows from organizations to avoid stale entries
    # (the existing 3 generic rows like "Acme Corp" are placeholders).
    # We refuse to delete if there are foreign references - the contacts
    # table sets organization_id to one of these old UUIDs in 2 rows, so
    # we first clear those references.
    logger.info("Clearing stale organization_id references in contacts...")
    try:
        await db.table("contacts").update({"organization_id": None}).not_.is_(
            "organization_id", "null"
        ).execute()
    except Exception as e:
        logger.warning(f"Could not clear stale contact org refs: {e}")

    logger.info("Deleting old organization rows...")
    try:
        # Get list of existing org ids
        existing = await db.table("organizations").select("id").execute()
        existing_ids = [o["id"] for o in (existing.data or [])]
        if existing_ids:
            for batch_start in range(0, len(existing_ids), 100):
                batch = existing_ids[batch_start:batch_start + 100]
                await db.table("organizations").delete().in_("id", batch).execute()
        logger.info(f"Deleted {len(existing_ids)} old organization rows")
    except Exception as e:
        logger.warning(f"Could not delete old orgs: {e}")

    # Insert new orgs in batches of 100
    logger.info("Inserting fresh organization records...")
    inserted = 0
    batch_size = 100
    for i in range(0, len(org_records), batch_size):
        batch = org_records[i:i + batch_size]
        try:
            await db.table("organizations").insert(batch).execute()
            inserted += len(batch)
            if inserted % 500 == 0:
                logger.info(f"  Inserted {inserted}/{len(org_records)}...")
        except Exception as e:
            logger.error(f"Failed batch insert: {e}")
            # Try individually
            for record in batch:
                try:
                    await db.table("organizations").insert(record).execute()
                    inserted += 1
                except Exception as inner_e:
                    logger.debug(f"Skipping org {record['id']}: {inner_e}")

    logger.info(f"Total inserted: {inserted}/{len(org_records)}")
    return pipedrive_to_uuid


async def update_contact_relationships(
    db: Any, pipedrive: PipedriveClient, org_map: Dict[int, str]
) -> Dict[str, int]:
    """Update contacts with their organization (pipedrive_org_id + UUID)"""
    logger.info("Fetching all persons from Pipedrive for relationship update...")
    persons = await pipedrive.get_all_persons()
    logger.info(f"Got {len(persons)} persons")

    updates_by_pd_org: Dict[int, List[int]] = {}  # pipedrive_org_id -> list of pipedrive_person_ids
    no_org_person_ids: List[int] = []

    for person in persons:
        person_id = person.get("id")
        if not person_id:
            continue

        org_id = extract_person_org_id(person)
        if org_id and org_id in org_map:
            updates_by_pd_org.setdefault(org_id, []).append(person_id)
        else:
            no_org_person_ids.append(person_id)

    stats = {
        "linked_to_org": sum(len(v) for v in updates_by_pd_org.values()),
        "without_org": len(no_org_person_ids),
        "total": len(persons),
    }

    logger.info(f"Contacts with organization: {stats['linked_to_org']}")
    logger.info(f"Contacts without organization: {stats['without_org']}")

    # Update each group of contacts (same pipedrive_org_id) in one query
    logger.info("Updating contacts.pipedrive_org_id + organization_id...")
    updated = 0
    for pd_org_id, person_ids in updates_by_pd_org.items():
        org_uuid = org_map[pd_org_id]
        batch_size = 100
        for i in range(0, len(person_ids), batch_size):
            batch_ids = person_ids[i:i + batch_size]
            try:
                await db.table("contacts").update({
                    "pipedrive_org_id": pd_org_id,
                    "organization_id": org_uuid,
                }).in_("pipedrive_person_id", batch_ids).execute()
                updated += len(batch_ids)
                if updated % 500 == 0:
                    logger.info(f"  Updated {updated} contacts...")
            except Exception as e:
                logger.error(f"Failed update batch for org {pd_org_id}: {e}")

    # Clear pipedrive_org_id + organization_id for contacts without org
    if no_org_person_ids:
        logger.info(f"Clearing org links for {len(no_org_person_ids)} contacts without org...")
        for i in range(0, len(no_org_person_ids), 100):
            batch_ids = no_org_person_ids[i:i + 100]
            try:
                await db.table("contacts").update({
                    "pipedrive_org_id": None,
                    "organization_id": None,
                }).in_("pipedrive_person_id", batch_ids).execute()
            except Exception as e:
                logger.error(f"Failed clearing batch: {e}")

    stats["updated"] = updated
    return stats


async def verify_job_relationships(db: Any) -> Dict[str, int]:
    """Check that jobs have proper person_id and org_id"""
    logger.info("Verifying job relationships...")
    total = await db.table("jobs").select("id", count="exact").execute()
    with_org = await db.table("jobs").select("id", count="exact").not_.is_("org_id", "null").execute()
    with_person = await db.table("jobs").select("id", count="exact").not_.is_("person_id", "null").execute()

    return {
        "total": total.count or 0,
        "with_org_id": with_org.count or 0,
        "with_person_id": with_person.count or 0,
    }


async def main():
    await init_supabase()
    db = await get_supabase_client()

    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    # Step 1: Sync organizations
    print("\n" + "=" * 70)
    print("STEP 1: SYNCING ORGANIZATIONS")
    print("=" * 70)
    org_map = await sync_organizations(db, pipedrive)

    # Step 2: Update contact-org relationships
    print("\n" + "=" * 70)
    print("STEP 2: UPDATING CONTACT-ORGANIZATION RELATIONSHIPS")
    print("=" * 70)
    contact_stats = await update_contact_relationships(db, pipedrive, org_map)

    # Step 3: Verify job relationships
    print("\n" + "=" * 70)
    print("STEP 3: VERIFYING JOB RELATIONSHIPS")
    print("=" * 70)
    job_stats = await verify_job_relationships(db)

    # Log sync to db
    try:
        await db.table("pipedrive_sync_log").insert({
            "entity_type": "organizations",
            "sync_direction": "inbound",
            "status": "completed",
            "total_records": len(org_map),
            "created_count": len(org_map),
            "updated_count": 0,
            "failed_count": 0,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "details": {
                "orgs_synced": len(org_map),
                "contacts_linked": contact_stats["linked_to_org"],
            },
        }).execute()
    except Exception as e:
        logger.warning(f"Could not log sync: {e}")

    await pipedrive.close()

    # Final summary
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Organizations synced:                  {len(org_map)}")
    print()
    print(f"Total persons in Pipedrive:            {contact_stats['total']}")
    print(f"  → Linked to organization:            {contact_stats['linked_to_org']}")
    print(f"  → Without organization:              {contact_stats['without_org']}")
    print(f"  → Total updated:                     {contact_stats['updated']}")
    print()
    print(f"Total jobs in DB:                      {job_stats['total']}")
    print(f"  → With org_id (Pipedrive):           {job_stats['with_org_id']}")
    print(f"  → With person_id (Pipedrive):        {job_stats['with_person_id']}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
