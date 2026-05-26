"""
Fix contacts categorization based on the 'סטטוס איש הקשר' custom field in Pipedrive.

Custom field: ab0c233f11f664275203977ddd33194795e485b2
Mapping:
- id=4   'עובד חברה'        -> employee
- id=34  'לקוח'              -> client
- id=33  'לקוח פוטנציאלי'    -> potential_client
- id=5   'מועמד לחברה'       -> candidate
- id=375 'מועמד בתהליך'       -> candidate
- id=144 'עובד לשעבר'         -> former_employee
- id=30  'קבלן משנה'          -> subcontractor
- id=35  'שותף עסקי'          -> business_partner
- None/missing                -> uncategorized
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.supabase import get_supabase_client, init_supabase
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Custom field key for contact status
CONTACT_STATUS_FIELD = "ab0c233f11f664275203977ddd33194795e485b2"

# Option ID -> contact_status mapping
STATUS_MAPPING = {
    4: "employee",            # עובד חברה
    34: "client",             # לקוח
    33: "potential_client",   # לקוח פוטנציאלי
    5: "candidate",           # מועמד לחברה
    375: "candidate",         # מועמד בתהליך
    144: "former_employee",   # עובד לשעבר
    30: "subcontractor",      # קבלן משנה
    35: "business_partner",   # שותף עסקי
}

# Hebrew labels for logging
STATUS_LABELS = {
    "employee": "עובד חברה",
    "client": "לקוח",
    "potential_client": "לקוח פוטנציאלי",
    "candidate": "מועמד",
    "former_employee": "עובד לשעבר",
    "subcontractor": "קבלן משנה",
    "business_partner": "שותף עסקי",
    "uncategorized": "ללא סטטוס",
}


def map_status_id_to_string(status_id) -> str:
    """Map Pipedrive option id to our contact_status string"""
    if status_id is None or status_id == "":
        return "uncategorized"

    try:
        # The field can come as int, str, or comma-separated string of ids
        if isinstance(status_id, str):
            # Sometimes Pipedrive returns "33" or "33,34" - take the first one
            first = status_id.split(",")[0].strip()
            if not first:
                return "uncategorized"
            status_id = int(first)
        elif isinstance(status_id, list):
            if not status_id:
                return "uncategorized"
            status_id = int(status_id[0])
        else:
            status_id = int(status_id)
    except (ValueError, TypeError):
        return "uncategorized"

    return STATUS_MAPPING.get(status_id, "uncategorized")


async def categorize_contacts_by_pipedrive_field():
    """Re-categorize all contacts based on the contact status custom field"""
    db = await get_supabase_client()
    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    logger.info("Fetching all persons from Pipedrive...")
    persons = await pipedrive.get_all_persons()
    logger.info(f"Fetched {len(persons)} persons")

    # Group persons by their contact status (from custom field)
    status_groups: Dict[str, List[int]] = {}

    for person in persons:
        person_id = person.get("id")
        if not person_id:
            continue

        status_value = person.get(CONTACT_STATUS_FIELD)
        status_str = map_status_id_to_string(status_value)

        status_groups.setdefault(status_str, []).append(person_id)

    # Print summary
    logger.info("=" * 60)
    logger.info("Categorization from Pipedrive custom field:")
    logger.info("=" * 60)
    for status, ids in sorted(status_groups.items(), key=lambda x: -len(x[1])):
        label = STATUS_LABELS.get(status, status)
        logger.info(f"  {status:20s} ({label}): {len(ids)}")

    # Update DB: set contact_status for each group
    for status, person_ids in status_groups.items():
        if not person_ids:
            continue

        logger.info(f"Updating {len(person_ids)} contacts to status='{status}'...")

        batch_size = 100
        updated = 0
        for i in range(0, len(person_ids), batch_size):
            batch = person_ids[i:i + batch_size]
            try:
                await db.table("contacts").update({
                    "contact_status": status,
                }).in_("pipedrive_person_id", batch).execute()
                updated += len(batch)
            except Exception as e:
                logger.error(f"Failed batch: {e}")

        logger.info(f"  Updated {updated}/{len(person_ids)} contacts to '{status}'")

    await pipedrive.close()
    return status_groups


async def main():
    await init_supabase()
    groups = await categorize_contacts_by_pipedrive_field()

    print("\n" + "=" * 60)
    print("FINAL CONTACTS CATEGORIZATION (from Pipedrive 'סטטוס איש הקשר')")
    print("=" * 60)
    total = sum(len(ids) for ids in groups.values())
    for status, ids in sorted(groups.items(), key=lambda x: -len(x[1])):
        label = STATUS_LABELS.get(status, status)
        pct = (len(ids) / total * 100) if total else 0
        print(f"  {status:20s} ({label:20s}): {len(ids):5d} ({pct:5.1f}%)")
    print("=" * 60)
    print(f"  Total: {total}")


if __name__ == "__main__":
    asyncio.run(main())
