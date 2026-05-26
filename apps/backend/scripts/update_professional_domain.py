"""
Update professional_domain for all contacts based on the 'תחום מקצועי' custom field in Pipedrive.

Custom field key: 46b46ea96edb7a1408ac6930f25f32d704f70b53
Field type: 'set' (multi-select) - returns comma-separated option ids

The script:
1. Fetches the full id -> label mapping from Pipedrive personFields
2. Iterates all persons and converts their numeric ids to Hebrew labels
3. Stores comma-separated labels in contacts.professional_domain
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.supabase import get_supabase_client, init_supabase
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

# Custom field key for "תחום מקצועי" (multi-select)
PROFESSIONAL_DOMAIN_FIELD = "46b46ea96edb7a1408ac6930f25f32d704f70b53"


async def fetch_domain_options_map(pipedrive: PipedriveClient) -> Dict[int, str]:
    """Fetch the option id -> label mapping for professional_domain field"""
    logger.info("Fetching person fields from Pipedrive to build domain map...")
    response = await pipedrive._make_request_with_retry("GET", "/v1/personFields")
    if not response.get("success"):
        raise RuntimeError(f"Failed to fetch personFields: {response.get('error')}")

    fields = response.get("data", [])
    target_field = None
    for field in fields:
        if field.get("key") == PROFESSIONAL_DOMAIN_FIELD:
            target_field = field
            break

    if not target_field:
        raise RuntimeError(f"Field {PROFESSIONAL_DOMAIN_FIELD} not found in personFields")

    options = target_field.get("options", []) or []
    options_map: Dict[int, str] = {}
    for opt in options:
        opt_id = opt.get("id")
        label = opt.get("label", "").strip()
        if opt_id is not None and label:
            options_map[int(opt_id)] = label

    logger.info(f"Built domain map with {len(options_map)} options")
    return options_map


def parse_domain_value(value: Any, options_map: Dict[int, str]) -> Optional[str]:
    """
    Convert the raw professional_domain field value to a comma-separated string of labels.

    The field is a 'set' so value can be:
    - None / "" - no value
    - "378" - single option as string
    - "378,346" - multiple options comma-separated
    - 378 - single option as int
    - [378, 346] - list of ints
    """
    if value is None or value == "":
        return None

    ids: List[int] = []

    if isinstance(value, list):
        for item in value:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
    elif isinstance(value, str):
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                continue
    else:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            return None

    labels = [options_map[i] for i in ids if i in options_map]
    return ", ".join(labels) if labels else None


async def update_contacts_professional_domain():
    """Update professional_domain for all contacts"""
    db = await get_supabase_client()
    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )

    options_map = await fetch_domain_options_map(pipedrive)

    logger.info("Fetching all persons from Pipedrive...")
    persons = await pipedrive.get_all_persons()
    logger.info(f"Got {len(persons)} persons")

    # Build pipedrive_person_id -> professional_domain mapping
    domain_updates: List[tuple] = []  # (person_id, domain_string)
    domain_counts: Dict[str, int] = {}  # for stats

    for person in persons:
        person_id = person.get("id")
        if not person_id:
            continue

        raw_value = person.get(PROFESSIONAL_DOMAIN_FIELD)
        domain_str = parse_domain_value(raw_value, options_map)

        if domain_str:
            domain_updates.append((person_id, domain_str))
            # Count individual domain occurrences for stats
            for d in domain_str.split(", "):
                domain_counts[d] = domain_counts.get(d, 0) + 1

    logger.info(f"Found {len(domain_updates)} persons with professional_domain set")

    # Print top domains
    if domain_counts:
        logger.info("Top 10 domain occurrences:")
        sorted_domains = sorted(domain_counts.items(), key=lambda x: -x[1])
        for domain, count in sorted_domains[:10]:
            logger.info(f"  {domain}: {count}")

    # Update DB in batches (one update per person, since values are unique)
    updated = 0
    failed = 0
    batch_log_every = 100

    for person_id, domain_str in domain_updates:
        try:
            await db.table("contacts").update({
                "professional_domain": domain_str,
            }).eq("pipedrive_person_id", person_id).execute()
            updated += 1
            if updated % batch_log_every == 0:
                logger.info(f"Updated {updated}/{len(domain_updates)}...")
        except Exception as e:
            logger.error(f"Failed for person {person_id}: {e}")
            failed += 1

    # Clear professional_domain for contacts that don't have it in Pipedrive
    # (so stale data is removed)
    persons_with_domain = {p[0] for p in domain_updates}
    all_pipedrive_ids = {p["id"] for p in persons if p.get("id")}
    persons_without_domain = all_pipedrive_ids - persons_with_domain

    if persons_without_domain:
        logger.info(f"Clearing professional_domain for {len(persons_without_domain)} contacts without value...")
        # Process in batches of 100
        person_id_list = list(persons_without_domain)
        cleared = 0
        for i in range(0, len(person_id_list), 100):
            batch_ids = person_id_list[i:i + 100]
            try:
                await db.table("contacts").update({
                    "professional_domain": None,
                }).in_("pipedrive_person_id", batch_ids).execute()
                cleared += len(batch_ids)
            except Exception as e:
                logger.error(f"Error clearing batch: {e}")
        logger.info(f"Cleared {cleared} stale professional_domain values")

    await pipedrive.close()

    return {
        "total_persons": len(persons),
        "with_domain": len(domain_updates),
        "without_domain": len(persons_without_domain),
        "updated": updated,
        "failed": failed,
        "top_domains": sorted(domain_counts.items(), key=lambda x: -x[1])[:15],
    }


async def main():
    await init_supabase()
    result = await update_contacts_professional_domain()

    print("\n" + "=" * 70)
    print("PROFESSIONAL DOMAIN UPDATE RESULT")
    print("=" * 70)
    print(f"  Total persons in Pipedrive: {result['total_persons']}")
    print(f"  With professional_domain:    {result['with_domain']}")
    print(f"  Without (cleared):           {result['without_domain']}")
    print(f"  Successfully updated:        {result['updated']}")
    print(f"  Failed:                      {result['failed']}")
    print()
    print(f"  Top 15 domains by count:")
    for domain, count in result["top_domains"]:
        print(f"    {domain:30s}: {count}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
