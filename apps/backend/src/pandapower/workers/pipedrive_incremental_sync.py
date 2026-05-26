"""
Incremental Pipedrive Sync Worker
Syncs only recently modified contacts from Pipedrive to PandaPower.
Uses proper update-or-insert pattern to avoid duplicates.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings
from pandapower.integrations.pipedrive_client import PipedriveClient

logger = logging.getLogger(__name__)

# Same namespace as pipedrive_sync.py - for deterministic org UUIDs
ORG_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def pipedrive_org_id_to_uuid(pipedrive_org_id: int) -> str:
    """Generate deterministic UUID for org based on Pipedrive id"""
    return str(uuid.uuid5(ORG_NAMESPACE, f"pipedrive_org:{pipedrive_org_id}"))


def _extract_person_org_id(person: Dict[str, Any]) -> Optional[int]:
    """Extract organization id from a person object"""
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


async def sync_pipedrive_contacts_incremental(minutes_back: int = 60) -> Dict[str, Any]:
    """
    Sync recently modified contacts from Pipedrive to PandaPower.

    Args:
        minutes_back: How many minutes back to check for changes (default: 60)

    Returns:
        Sync summary with counts
    """
    sync_start_time = datetime.utcnow()
    try:
        db = await get_supabase_client()

        pipedrive = PipedriveClient(
            api_token=settings.PIPEDRIVE_API_TOKEN,
            api_domain=settings.PIPEDRIVE_API_DOMAIN
        )

        since_timestamp = datetime.utcnow() - timedelta(minutes=minutes_back)
        logger.info(f"Starting incremental contacts sync (last {minutes_back} minutes)...")

        # Build option mapping for professional_domain
        domain_options_map = await _build_domain_options_map(pipedrive)

        persons = await pipedrive.get_all_persons()

        # Filter to only recently modified
        recent_persons = [p for p in persons if _is_recently_modified(p, since_timestamp)]
        logger.info(f"Found {len(recent_persons)} recently modified persons out of {len(persons)} total")

        summary = {
            "total_fetched": len(recent_persons),
            "employees": 0,
            "clients": 0,
            "potential_clients": 0,
            "errors": [],
            "minutes_back": minutes_back,
        }

        for person in recent_persons:
            try:
                contact_status = _categorize_contact(person)

                # Extract org links
                pd_org_id = _extract_person_org_id(person)
                org_uuid = pipedrive_org_id_to_uuid(pd_org_id) if pd_org_id else None

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

                await _sync_contact(db, person_data)

                if contact_status == "employee":
                    summary["employees"] += 1
                elif contact_status == "client":
                    summary["clients"] += 1
                else:
                    summary["potential_clients"] += 1

            except Exception as e:
                logger.error(f"Error syncing person {person.get('id')}: {str(e)}")
                summary["errors"].append({
                    "person_id": person.get('id'),
                    "error": str(e)
                })

        await pipedrive.close()

        await _log_sync_completion(db, "persons", summary, sync_start_time)

        logger.info(f"Incremental sync completed: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Pipedrive incremental sync failed: {str(e)}")
        raise


def _is_recently_modified(person: Dict[str, Any], since_timestamp: datetime) -> bool:
    """Check if person was modified after the given timestamp"""
    try:
        update_time = person.get('update_time')
        if not update_time:
            return False
        person_updated = datetime.fromisoformat(update_time.replace('Z', '+00:00'))
        # Make since_timestamp timezone-aware for comparison
        if since_timestamp.tzinfo is None:
            from datetime import timezone
            since_timestamp = since_timestamp.replace(tzinfo=timezone.utc)
        return person_updated > since_timestamp
    except Exception as e:
        logger.warning(f"Error checking update time for person: {e}")
        return False


# ---------------------------------------------------------------------------
# Pipedrive custom field keys for person fields
# ---------------------------------------------------------------------------
CONTACT_STATUS_FIELD = "ab0c233f11f664275203977ddd33194795e485b2"       # סטטוס איש הקשר
PROFESSIONAL_DOMAIN_FIELD = "46b46ea96edb7a1408ac6930f25f32d704f70b53"  # תחום מקצועי
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

# Module-level cache for professional_domain options
_DOMAIN_OPTIONS_CACHE: Dict[int, str] = {}


async def _build_domain_options_map(pipedrive: Any) -> Dict[int, str]:
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


def _categorize_contact(person: Dict[str, Any]) -> str:
    """Categorize contact based on the Pipedrive 'סטטוס איש הקשר' custom field"""
    status_value = person.get(CONTACT_STATUS_FIELD)

    if status_value is None or status_value == "":
        return "uncategorized"

    try:
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


async def _sync_contact(db: Any, person_data: Dict[str, Any]) -> None:
    """Sync contact using update-or-insert pattern (avoids duplicates)"""
    try:
        result = await db.table("contacts").update(person_data).eq(
            "pipedrive_person_id", person_data["pipedrive_person_id"]
        ).execute()

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
                "minutes_back": summary.get("minutes_back"),
                "employees": summary.get("employees", 0),
                "clients": summary.get("clients", 0),
                "potential_clients": summary.get("potential_clients", 0),
                "errors": summary.get("errors", []),
            },
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log sync: {str(e)}")
