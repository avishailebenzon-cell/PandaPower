"""
Pipedrive Sync Worker
Synchronizes contacts from Pipedrive to PandaPower database with proper categorization:
- employee (עובדים): linked to organization, no deals
- client (לקוחות): has won or open deals
- potential_client (לקוחות פוטנציאלים): everything else

Also keeps contact-organization relationships in sync:
- contacts.pipedrive_org_id: raw Pipedrive org id (BIGINT)
- contacts.organization_id: our internal UUID for the org (FK to organizations.id)
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

# Fixed namespace for deterministic UUIDs from Pipedrive org ids
# Must match the one in scripts/sync_orgs_and_relationships.py
ORG_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def pipedrive_org_id_to_uuid(pipedrive_org_id: int) -> str:
    """Generate a deterministic UUID for an organization based on its Pipedrive id"""
    return str(uuid.uuid5(ORG_NAMESPACE, f"pipedrive_org:{pipedrive_org_id}"))


def _extract_person_org_id(person: Dict[str, Any]) -> Optional[int]:
    """Extract organization id (int) from a Pipedrive person object"""
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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipedrive custom field keys for person fields
# ---------------------------------------------------------------------------
CONTACT_STATUS_FIELD = "ab0c233f11f664275203977ddd33194795e485b2"       # סטטוס איש הקשר
PROFESSIONAL_DOMAIN_FIELD = "46b46ea96edb7a1408ac6930f25f32d704f70b53"  # תחום מקצועי (multi-select)
SECURITY_CLEARANCE_FIELD = "ed60d224c8ddfc0a210361bdd88d9529ae22a301"   # סווג בטחוני

# Pipedrive option ID -> our contact_status string
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

# Security clearance option id -> label
SECURITY_CLEARANCE_MAPPING = {
    145: "רמה 1",
    146: "רמה 2",
    147: "רמה 3",
}

# Module-level cache for professional_domain options (option_id -> label).
# Populated on first sync call; refreshed when sync is triggered.
_DOMAIN_OPTIONS_CACHE: Dict[int, str] = {}


async def _build_domain_options_map(pipedrive: PipedriveClient) -> Dict[int, str]:
    """Fetch and cache professional_domain field option id -> label mapping"""
    global _DOMAIN_OPTIONS_CACHE
    try:
        response = await pipedrive._make_request_with_retry("GET", "/v1/personFields")
        if not response.get("success"):
            return _DOMAIN_OPTIONS_CACHE

        for field in response.get("data", []):
            if field.get("key") == PROFESSIONAL_DOMAIN_FIELD:
                options = field.get("options", []) or []
                mapping: Dict[int, str] = {}
                for opt in options:
                    opt_id = opt.get("id")
                    label = opt.get("label", "").strip()
                    if opt_id is not None and label:
                        mapping[int(opt_id)] = label
                _DOMAIN_OPTIONS_CACHE = mapping
                logger.info(f"Loaded {len(mapping)} professional_domain options")
                break
    except Exception as e:
        logger.error(f"Failed to load professional_domain options: {e}")
    return _DOMAIN_OPTIONS_CACHE


def _parse_professional_domain(value: Any, options_map: Dict[int, str]) -> Optional[str]:
    """Convert a multi-select value (option ids) to comma-separated labels"""
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


def _parse_security_clearance(value: Any) -> Optional[str]:
    """Convert security clearance option id to Hebrew label"""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            first = value.split(",")[0].strip()
            if not first:
                return None
            option_id = int(first)
        elif isinstance(value, list):
            if not value:
                return None
            option_id = int(value[0])
        else:
            option_id = int(value)
    except (ValueError, TypeError):
        return None

    return SECURITY_CLEARANCE_MAPPING.get(option_id)


async def sync_pipedrive_contacts(since: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Sync contacts from Pipedrive to PandaPower with proper categorization.

    Args:
        since: if provided, only fetch persons/organizations changed since this
            timestamp (delta sync via /v1/recents). If None, a full sync is done.
            Upserts are idempotent, so delta only ever touches changed rows and
            never disturbs existing data.

    Returns:
        Sync summary with counts
    """
    sync_start_time = datetime.utcnow()
    try:
        db = await get_supabase_client()

        # Initialize Pipedrive client
        pipedrive = PipedriveClient(
            api_token=settings.PIPEDRIVE_API_TOKEN,
            api_domain=settings.PIPEDRIVE_API_DOMAIN
        )

        # Fetch persons from Pipedrive
        sync_mode = "delta" if since is not None else "full"
        logger.info(f"Starting Pipedrive contacts sync ({sync_mode})...")

        # Build option mapping for professional_domain
        domain_options_map = await _build_domain_options_map(pipedrive)

        # Sync organizations first (so contact->org relationships work).
        # In delta mode a newly-created org appears in its own /recents feed,
        # and orgs are synced before persons, so contact->org links stay valid.
        await _sync_organizations(db, pipedrive, since=since)

        persons = await pipedrive.get_all_persons(since=since)
        logger.info(f"Fetched {len(persons)} persons from Pipedrive ({sync_mode})")

        # Sync summary
        summary = {
            "total_fetched": len(persons),
            "employees": 0,
            "clients": 0,
            "potential_clients": 0,
            "candidates": 0,
            "former_employees": 0,
            "subcontractors": 0,
            "business_partners": 0,
            "uncategorized": 0,
            "errors": [],
        }

        # Process in batches of 500 to avoid timeouts
        batch_size = 500
        for batch_idx in range(0, len(persons), batch_size):
            batch = persons[batch_idx:batch_idx + batch_size]
            batch_num = (batch_idx // batch_size) + 1
            total_batches = (len(persons) + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} persons)")

            for person in batch:
                try:
                    # Categorize contact
                    contact_status = _categorize_contact(person)

                    # Extract organization id and our internal UUID
                    pd_org_id = _extract_person_org_id(person)
                    org_uuid = pipedrive_org_id_to_uuid(pd_org_id) if pd_org_id else None

                    # Prepare person data with all custom field mappings
                    person_data = {
                        "pipedrive_person_id": person.get('id'),
                        "full_name": person.get('name', ''),
                        "email": _extract_email(person),
                        "phone": _extract_phone(person),
                        "contact_status": contact_status,
                        "professional_domain": _parse_professional_domain(
                            person.get(PROFESSIONAL_DOMAIN_FIELD), domain_options_map
                        ),
                        "security_clearance_level": _parse_security_clearance(
                            person.get(SECURITY_CLEARANCE_FIELD)
                        ),
                        "pipedrive_org_id": pd_org_id,
                        "organization_id": org_uuid,
                        "pipedrive_last_synced_at": datetime.utcnow().isoformat(),
                        "updated_at": datetime.utcnow().isoformat(),
                    }

                    # Sync to contacts table with update-or-insert pattern
                    await _sync_contact(db, person_data)

                    # Update counters
                    counter_map = {
                        "employee": "employees",
                        "client": "clients",
                        "potential_client": "potential_clients",
                        "candidate": "candidates",
                        "former_employee": "former_employees",
                        "subcontractor": "subcontractors",
                        "business_partner": "business_partners",
                        "uncategorized": "uncategorized",
                    }
                    counter_key = counter_map.get(contact_status, "uncategorized")
                    summary[counter_key] = summary.get(counter_key, 0) + 1

                except Exception as e:
                    logger.error(f"Error syncing person {person.get('id')}: {str(e)}")
                    summary["errors"].append({
                        "person_id": person.get('id'),
                        "error": str(e)
                    })

            logger.info(
                f"Batch {batch_num}/{total_batches} done. "
                f"Employees: {summary['employees']}, "
                f"Clients: {summary['clients']}, "
                f"Potential: {summary['potential_clients']}"
            )

        # Close Pipedrive client
        await pipedrive.close()

        # Log sync completion
        await _log_sync_completion(db, "persons", summary, sync_start_time)

        logger.info(f"Sync completed: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Pipedrive sync failed: {str(e)}")
        raise


def _categorize_contact(person: Dict[str, Any]) -> str:
    """
    Categorize a contact based on the 'סטטוס איש הקשר' custom field in Pipedrive.

    The field is identified by key 'ab0c233f11f664275203977ddd33194795e485b2'.
    Returns the canonical status string mapped from the field's option id.
    """
    status_value = person.get(CONTACT_STATUS_FIELD)

    if status_value is None or status_value == "":
        return "uncategorized"

    try:
        # Pipedrive returns option id as int, str, or comma-separated string of ids
        if isinstance(status_value, str):
            first = status_value.split(",")[0].strip()
            if not first:
                return "uncategorized"
            status_id = int(first)
        elif isinstance(status_value, list):
            if not status_value:
                return "uncategorized"
            status_id = int(status_value[0])
        else:
            status_id = int(status_value)
    except (ValueError, TypeError):
        return "uncategorized"

    return STATUS_MAPPING.get(status_id, "uncategorized")


def _extract_email(person: Dict[str, Any]) -> Optional[str]:
    """Extract email from person object"""
    emails = person.get("email", [])
    if emails and len(emails) > 0:
        if isinstance(emails[0], dict):
            return emails[0].get("value")
        return emails[0]
    return None


def _extract_phone(person: Dict[str, Any]) -> Optional[str]:
    """Extract phone from person object"""
    phones = person.get("phone", [])
    if phones and len(phones) > 0:
        if isinstance(phones[0], dict):
            return phones[0].get("value")
        return phones[0]
    return None


async def sync_pipedrive_organizations(since: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Sync ONLY organizations from Pipedrive (lightweight).

    Used by the scheduler's `organizations` entity so it does NOT re-trigger a
    full contacts sync (which would re-fetch every person and double the API
    cost). The `persons` sync still syncs orgs first for contact->org FK safety;
    this just keeps the org table fresh on its own cadence.
    """
    sync_start_time = datetime.utcnow()
    db = await get_supabase_client()
    pipedrive = PipedriveClient(
        api_token=settings.PIPEDRIVE_API_TOKEN,
        api_domain=settings.PIPEDRIVE_API_DOMAIN,
    )
    try:
        synced = await _sync_organizations(db, pipedrive, since=since)
        return {"total_fetched": synced, "synced": synced}
    finally:
        await pipedrive.close()


async def _sync_organizations(
    db: Any, pipedrive: PipedriveClient, since: Optional[datetime] = None
) -> int:
    """
    Sync organizations from Pipedrive into the organizations table.
    Uses deterministic UUIDs based on pipedrive_org_id.

    If `since` is provided, only organizations changed since that timestamp are
    fetched (delta). Returns the number of organizations synced.
    """
    try:
        mode = "delta" if since is not None else "full"
        logger.info(f"Syncing organizations from Pipedrive ({mode})...")
        orgs = await pipedrive.get_all_organizations(since=since)
        logger.info(f"Got {len(orgs)} organizations from Pipedrive")

        synced = 0
        for org in orgs:
            pd_id = org.get("id")
            name = org.get("name")
            if not pd_id or not name:
                continue

            org_uuid = pipedrive_org_id_to_uuid(pd_id)
            try:
                # Try update first
                result = await db.table("organizations").update({
                    "name": name,
                }).eq("id", org_uuid).execute()

                # Insert if doesn't exist
                if not result.data or len(result.data) == 0:
                    await db.table("organizations").insert({
                        "id": org_uuid,
                        "name": name,
                    }).execute()
                synced += 1
            except Exception as e:
                logger.debug(f"Skipping org {pd_id} ({name}): {e}")

        logger.info(f"Synced {synced} organizations")
        return synced
    except Exception as e:
        logger.error(f"Organization sync failed: {e}")
        return 0


async def _sync_contact(db: Any, person_data: Dict[str, Any]) -> None:
    """
    Sync contact to contacts table using update-or-insert pattern.
    Avoids duplicate creation when pipedrive_person_id already exists.
    """
    try:
        # Try to update existing record first
        result = await db.table("contacts").update(person_data).eq(
            "pipedrive_person_id", person_data["pipedrive_person_id"]
        ).execute()

        # If no records were updated, insert as new record
        if not result.data or len(result.data) == 0:
            await db.table("contacts").insert(person_data).execute()
    except Exception as e:
        logger.error(f"Failed to sync contact {person_data.get('pipedrive_person_id')}: {str(e)}")
        raise


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
            "created_count": (
                summary.get("employees", 0)
                + summary.get("clients", 0)
                + summary.get("potential_clients", 0)
            ),
            "updated_count": 0,
            "failed_count": len(summary.get("errors", [])),
            "started_at": sync_start_time.isoformat(),
            "completed_at": sync_end_time.isoformat(),
            "duration_ms": duration_ms,
            "details": {
                "employees": summary.get("employees", 0),
                "clients": summary.get("clients", 0),
                "potential_clients": summary.get("potential_clients", 0),
                "errors": summary.get("errors", []),
            },
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log sync: {str(e)}")
