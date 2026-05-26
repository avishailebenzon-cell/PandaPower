"""
Fix duplicate contacts in the database and categorize them properly.

This script:
1. Removes duplicate contacts (keeps newest record per pipedrive_person_id)
2. Categorizes contacts based on Pipedrive data:
   - employee: linked to company organization
   - client: linked to won deals
   - potential_client: everything else
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any, List

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.supabase import get_supabase_client, init_supabase
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


async def deduplicate_contacts():
    """
    Remove duplicate contacts from the database.
    Keeps the newest record (most recent updated_at) per pipedrive_person_id.
    """
    db = await get_supabase_client()

    logger.info("Starting contacts deduplication...")

    # Fetch all contacts with their key fields, ordered by updated_at DESC
    # We need pagination because there could be 45k+ records
    all_contacts = []
    page_size = 1000
    offset = 0

    while True:
        response = await db.table("contacts").select(
            "id, pipedrive_person_id, updated_at"
        ).order("updated_at", desc=True).range(offset, offset + page_size - 1).execute()

        batch = response.data or []
        if not batch:
            break

        all_contacts.extend(batch)
        logger.info(f"Loaded {len(all_contacts)} contacts...")
        offset += page_size

        if len(batch) < page_size:
            break

    logger.info(f"Total contacts in DB: {len(all_contacts)}")

    # Track first occurrence (newest) per pipedrive_person_id
    seen_person_ids = {}
    ids_to_delete = []

    for contact in all_contacts:
        person_id = contact["pipedrive_person_id"]
        if person_id is None:
            # Records without pipedrive_person_id - skip
            continue

        if person_id in seen_person_ids:
            # This is a duplicate (older record)
            ids_to_delete.append(contact["id"])
        else:
            seen_person_ids[person_id] = contact["id"]

    logger.info(f"Unique pipedrive_person_ids: {len(seen_person_ids)}")
    logger.info(f"Duplicate records to delete: {len(ids_to_delete)}")

    # Delete duplicates in batches of 100
    deleted_count = 0
    batch_size = 100
    for i in range(0, len(ids_to_delete), batch_size):
        batch_ids = ids_to_delete[i:i + batch_size]
        try:
            await db.table("contacts").delete().in_("id", batch_ids).execute()
            deleted_count += len(batch_ids)
            logger.info(f"Deleted {deleted_count}/{len(ids_to_delete)} duplicates...")
        except Exception as e:
            logger.error(f"Error deleting batch: {e}")

    logger.info(f"Deduplication complete. Deleted {deleted_count} duplicate records.")
    return len(seen_person_ids)


async def categorize_contacts():
    """
    Categorize contacts based on their Pipedrive data:
    - employee: linked to company organization
    - client: linked to won deals
    - potential_client: everything else
    """
    db = await get_supabase_client()
    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    logger.info("Starting contacts categorization...")

    # Get all persons with their deal/org info from Pipedrive
    logger.info("Fetching persons from Pipedrive...")
    persons = await pipedrive.get_all_persons()
    logger.info(f"Got {len(persons)} persons from Pipedrive")

    # Build categorization
    categories = {
        "employee": [],
        "client": [],
        "potential_client": [],
    }

    for person in persons:
        person_id = person.get("id")
        if not person_id:
            continue

        # Check for won deals
        won_deals_count = person.get("won_deals_count", 0)
        open_deals_count = person.get("open_deals_count", 0)
        org_id = person.get("org_id")
        if isinstance(org_id, dict):
            org_id = org_id.get("value")

        # Categorization logic:
        # - If has won deals -> client
        # - If linked to organization and no deals -> employee
        # - Otherwise -> potential_client
        if won_deals_count and won_deals_count > 0:
            category = "client"
        elif open_deals_count and open_deals_count > 0:
            category = "client"  # In-progress deals = active client
        elif org_id:
            category = "employee"
        else:
            category = "potential_client"

        categories[category].append(person_id)

    logger.info(f"Categorization results:")
    logger.info(f"  Employees: {len(categories['employee'])}")
    logger.info(f"  Clients: {len(categories['client'])}")
    logger.info(f"  Potential Clients: {len(categories['potential_client'])}")

    # Update contact_status in database for each category
    for category, person_ids in categories.items():
        if not person_ids:
            continue

        logger.info(f"Updating {len(person_ids)} contacts to status '{category}'...")
        # Update in batches of 100
        batch_size = 100
        updated_count = 0
        for i in range(0, len(person_ids), batch_size):
            batch_ids = person_ids[i:i + batch_size]
            try:
                await db.table("contacts").update({
                    "contact_status": category
                }).in_("pipedrive_person_id", batch_ids).execute()
                updated_count += len(batch_ids)
            except Exception as e:
                logger.error(f"Error updating batch: {e}")

        logger.info(f"Updated {updated_count} contacts to '{category}'")

    await pipedrive.close()
    return categories


async def main():
    await init_supabase()

    # Step 1: Remove duplicates
    unique_count = await deduplicate_contacts()
    logger.info(f"After dedup: {unique_count} unique contacts")

    # Step 2: Categorize them
    categories = await categorize_contacts()

    # Summary
    print("\n" + "=" * 60)
    print("CONTACTS FIX SUMMARY")
    print("=" * 60)
    print(f"Total unique contacts: {unique_count}")
    print(f"Employees:         {len(categories['employee'])}")
    print(f"Clients:           {len(categories['client'])}")
    print(f"Potential Clients: {len(categories['potential_client'])}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
