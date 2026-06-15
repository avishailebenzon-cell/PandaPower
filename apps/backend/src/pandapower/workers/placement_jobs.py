"""Create internal placement jobs ("משרות השמה") from recruitment-agency emails.

Sender domains in settings.PLACEMENT_JOB_SENDER_DOMAINS (default adamtotal.co.il,
birdaero.comeet-notifications.com) are treated as agency job vacancies rather
than candidate CVs. We parse the email with Haiku and insert a row into the
shared `jobs` table flagged is_placement=true / source='email_placement', with
NO Pipedrive deal. It is inserted unassigned (assigned_agent_code=NULL) so the
existing Carmit routing task (workers/tasks.py) picks it up automatically.
"""

import logging
import re
from typing import Any, Optional

from pandapower.agents.placement.parser import parse_placement_email
from pandapower.core.config import settings

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _placement_domains() -> list[str]:
    return [
        d.strip().lower()
        for d in (settings.PLACEMENT_JOB_SENDER_DOMAINS or "").split(",")
        if d.strip()
    ]


def _addr_matches(addr: str, domains: list[str]) -> bool:
    addr = addr.strip().lower()
    return any(addr.endswith("@" + d) or addr.endswith("." + d) for d in domains)


def placement_source_address(email_from: Optional[str], body: Optional[str]) -> Optional[str]:
    """The agency address driving this email — either the direct sender or, for a
    forwarded email, the first placement-domain address found in the body."""
    domains = _placement_domains()
    if email_from and _addr_matches(email_from, domains):
        return email_from.strip().lower()
    for m in _EMAIL_RE.findall(body or ""):
        if _addr_matches(m, domains):
            return m.strip().lower()
    return None


def is_placement_sender(email_from: Optional[str], body: Optional[str] = None) -> bool:
    """True if this is a placement-agency vacancy email — matched either by the
    sender address (direct) or by a placement-domain address in the body (when
    the email was forwarded into the mailbox, e.g. 'FW: ...')."""
    return placement_source_address(email_from, body) is not None


async def _next_placement_job_number(supabase: Any) -> str:
    """Sequential internal id PL-#### (best-effort; not strictly gap-free)."""
    try:
        resp = await (
            supabase.table("jobs")
            .select("job_number")
            .eq("is_placement", True)
            .not_.is_("job_number", "null")
            .order("job_number", desc=True)
            .limit(1)
            .execute()
        )
        if resp.data and resp.data[0].get("job_number"):
            last = resp.data[0]["job_number"].split("-")[-1]
            return f"PL-{int(last) + 1:04d}"
    except Exception as e:
        logger.debug(f"placement job_number lookup failed, defaulting: {e}")
    return "PL-0001"


async def _notify_new_placement_job(job_number: str, parsed: dict, source_email: Optional[str]) -> None:
    """Best-effort admin notification that a new placement vacancy was ingested.
    Uses a job-unique key so each new job notifies (no cooldown suppression).
    Never raises — a notification failure must not break ingestion."""
    try:
        from pandapower.integrations.alert_service import alert_admin

        loc = parsed.get("job_location") or "—"
        contact = parsed.get("contact_name") or "—"
        phone = parsed.get("contact_phone") or "—"
        await alert_admin(
            key=f"placement-job-{job_number}",
            subject=f"🔴 משרת השמה חדשה נקלטה: {parsed.get('job_title')}",
            details=(
                f"קוד: {job_number}\n"
                f"משרה: {parsed.get('job_title')}\n"
                f"מיקום: {loc}\n"
                f"חברת השמה: {source_email or '—'}\n"
                f"איש קשר: {contact} ({phone})\n\n"
                f"המשרה נכנסה למערכת כמשרת השמה (לא סונכרנה לפייפדרייב) וממתינה לניתוב לסוכן."
            ),
            severity="info",
            include_traceback=False,
        )
    except Exception as e:
        logger.debug(f"placement new-job notification failed (ignored): {e}")


# Map the existing-job column → the parsed-dict key, for backfill.
_BACKFILL_FIELDS = {
    "job_description": "job_description",
    "job_qualifications": "job_qualifications",
    "job_location": "job_location",
    "job_security_clearance": "job_security_clearance",
    "placement_contact_name": "contact_name",
    "placement_contact_phone": "contact_phone",
}


async def _backfill_existing(supabase: Any, existing: dict, parsed: dict) -> str:
    """Fill columns the existing placement job is missing from a later forward.
    Returns 'duplicate_ref_backfilled' if anything was written, else 'duplicate_ref'."""
    updates = {}
    for col, pkey in _BACKFILL_FIELDS.items():
        if not existing.get(col) and parsed.get(pkey):
            updates[col] = parsed[pkey]
    if not updates:
        return "duplicate_ref"
    try:
        await supabase.table("jobs").update(updates).eq("id", existing["id"]).execute()
        logger.info(f"Backfilled placement job {existing['id']} fields: {list(updates)}")
        return "duplicate_ref_backfilled"
    except Exception as e:
        logger.debug(f"placement backfill failed: {e}")
        return "duplicate_ref"


async def create_placement_job_from_email(
    supabase: Any,
    *,
    message_id: str,
    email_from: str,
    subject: str,
    body: str,
    received_at: Optional[str] = None,
) -> dict[str, Any]:
    """Parse an agency email and insert a placement job. Idempotent per message_id.

    Returns {"created": bool, "job_id": str|None, "reason": str}.
    """
    # Dedup: one placement job per source email.
    try:
        existing = await (
            supabase.table("jobs")
            .select("id")
            .eq("placement_outlook_message_id", message_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return {"created": False, "job_id": existing.data[0]["id"], "reason": "duplicate"}
    except Exception as e:
        logger.debug(f"placement dedup check failed (proceeding): {e}")

    parsed = await parse_placement_email(subject, body)
    if not parsed:
        return {"created": False, "job_id": None, "reason": "parse_failed"}

    # Dedup across re-forwards of the same vacancy: if the agency's external job
    # id was already ingested, don't create a second job — but backfill any
    # fields the earlier copy was missing (a later forward may parse cleaner).
    external_ref = parsed.get("external_job_ref")
    if external_ref:
        try:
            dup = await (
                supabase.table("jobs")
                .select(
                    "id, job_description, job_qualifications, job_location, "
                    "job_security_clearance, placement_contact_name, placement_contact_phone"
                )
                .eq("placement_external_ref", external_ref)
                .limit(1)
                .execute()
            )
            if dup.data:
                existing = dup.data[0]
                reason = await _backfill_existing(supabase, existing, parsed)
                return {"created": False, "job_id": existing["id"], "reason": reason}
        except Exception as e:
            logger.debug(f"placement external-ref dedup check failed (proceeding): {e}")

    job_number = await _next_placement_job_number(supabase)
    # Prefer the real agency address (handles forwarded emails) over the sender.
    source_email = placement_source_address(email_from, body) or email_from

    row = {
        "source": "email_placement",
        "is_placement": True,
        "pipedrive_deal_id": None,
        "job_number": job_number,
        "job_title": parsed["job_title"],
        "job_description": parsed["job_description"],
        "job_qualifications": parsed["job_qualifications"],
        "job_location": parsed["job_location"],
        "job_security_clearance": parsed["job_security_clearance"],
        "status": "open",
        "assigned_agent_code": None,  # Carmit routing task will assign
        "placement_source_email": source_email,
        "placement_contact_name": parsed["contact_name"],
        "placement_contact_phone": parsed["contact_phone"],
        "placement_outlook_message_id": message_id,
        "placement_external_ref": external_ref,
        "organization_name": parsed["contact_name"],  # agency as the "client" label
        "last_modified_by": "email_placement_ingest",
    }

    try:
        resp = await supabase.table("jobs").insert(row).execute()
        job_id = resp.data[0]["id"] if resp.data else None
        logger.info(
            f"Created placement job {job_number} ({parsed['job_title']!r}) "
            f"from {email_from} [msg {message_id}]"
        )
        await _notify_new_placement_job(job_number, parsed, source_email)
        return {"created": True, "job_id": job_id, "reason": "created"}
    except Exception as e:
        # Unique index race → another run inserted it first; treat as duplicate.
        if "duplicate key" in str(e).lower() or "uq_jobs_placement_msg" in str(e).lower():
            return {"created": False, "job_id": None, "reason": "duplicate"}
        logger.error(f"Failed to insert placement job from {message_id}: {e}", exc_info=True)
        return {"created": False, "job_id": None, "reason": f"insert_failed: {e}"}
