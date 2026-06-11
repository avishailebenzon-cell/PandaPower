"""Tool handlers for Pandius (candidate-facing agent)."""

from typing import Any, Optional
from uuid import UUID

import structlog

from pandapower.core.supabase import get_supabase_client
from pandapower.core.phone import to_international, phones_match

logger = structlog.get_logger(__name__)


async def _find_contact_by_phone(supabase, phone: str) -> Optional[dict]:
    """Find a contact matching ``phone`` tolerantly across number formats.

    Tries an exact match on the canonical international form first (fast path),
    then falls back to a tolerant national-tail comparison so "+972-58…",
    "0586…" and "97258…" all resolve to the same contact."""
    intl = to_international(phone)
    if not intl:
        return None
    res = await supabase.table("contacts").select(
        "id, full_name, email, contact_status, phone"
    ).eq("phone", intl).limit(1).execute()
    if res.data:
        return res.data[0]
    # Fallback: scan recent candidates and compare tolerantly. Bounded to keep
    # this cheap; exact-match above handles the canonical-stored common case.
    res2 = await supabase.table("contacts").select(
        "id, full_name, email, contact_status, phone"
    ).not_.is_("phone", "null").limit(2000).execute()
    for c in (res2.data or []):
        if phones_match(c.get("phone"), phone):
            return c
    return None


async def handle_identify_candidate(
    conversation_id: UUID,
    pandius_client_id: UUID,
    phone: str,
) -> dict[str, Any]:
    """Check if this phone already belongs to a known contact."""
    try:
        supabase = await get_supabase_client()
        contact = await _find_contact_by_phone(supabase, phone)

        if contact:
            return {
                "status": "found",
                "candidate_exists": True,
                "contact_id": contact["id"],
                "full_name": contact.get("full_name"),
                "email": contact.get("email"),
                # Internal guidance for the model — NOT shown to the candidate.
                # Don't blindly greet by the stored name: if the person introduces
                # themselves differently, trust what they say now and update.
                "guidance": (
                    "כבר קיים איש קשר עם המספר הזה. אם הפרטים תואמים — אפשר להמשיך "
                    "בלי לבקש שוב שם/מייל. אם המועמד מציג את עצמו אחרת מהשם השמור, "
                    "סמוך על מה שהוא אומר עכשיו ועדכן את הפרטים."
                ),
            }
        return {
            "status": "not_found",
            "candidate_exists": False,
            "guidance": "מועמד חדש — אסוף שם מלא ומייל, ואז קרא ל-save_candidate.",
        }
    except Exception as e:
        logger.error(f"identify_candidate failed: {e}", exc_info=True)
        return {"status": "error", "message": "סליחה, בעיה בזיהוי. נמשיך הלאה."}


async def handle_save_candidate(
    conversation_id: UUID,
    pandius_client_id: UUID,
    phone: str,
    first_name: str,
    last_name: str,
    email: str,
) -> dict[str, Any]:
    """Create the job seeker as a contact with status 'מועמד לחברה' (candidate)
    and sync to Pipedrive, then link them to the pandius_client row."""
    try:
        supabase = await get_supabase_client()
        full_name = f"{first_name} {last_name}".strip()
        # Store the canonical international form so future lookups match.
        phone = to_international(phone) or phone

        # Don't duplicate if a contact already exists for this phone. Refresh the
        # stored name/email with what the candidate just told us — the existing
        # row may be stale (e.g. a contact saved under this number long ago), and
        # the live conversation is the more authoritative source.
        existing_contact = await _find_contact_by_phone(supabase, phone)
        if existing_contact:
            contact_id = existing_contact["id"]
            updates = {}
            if full_name and full_name != existing_contact.get("full_name"):
                updates["full_name"] = full_name
            if email and email != existing_contact.get("email"):
                updates["email"] = email
            if updates:
                try:
                    await supabase.table("contacts").update(updates).eq(
                        "id", contact_id
                    ).execute()
                except Exception as e:
                    logger.warning(f"Failed to refresh existing contact: {e}")
            await _link_contact(supabase, pandius_client_id, contact_id, full_name, email)
            return {
                "status": "already_exists",
                "contact_id": contact_id,
                "message": "הפרטים שלך כבר שמורים אצלנו ✅",
            }

        pipedrive_person_id = None
        try:
            from pandapower.integrations.pipedrive import PipedriveClient
            from pandapower.core.config import settings
            from pandapower.workers.pipedrive_sync import CONTACT_STATUS_FIELD

            # Option id 5 = "מועמד לחברה" (candidate) in the PandaTech workspace.
            CONTACT_STATUS_CANDIDATE = 5

            if settings.PIPEDRIVE_API_TOKEN:
                pipedrive_client = PipedriveClient(
                    settings.PIPEDRIVE_API_TOKEN,
                    settings.PIPEDRIVE_API_DOMAIN or "https://api.pipedrive.com",
                )
                pd_person = await pipedrive_client.create_person(
                    name=full_name,
                    email=email,
                    phone=phone,
                    custom_fields={CONTACT_STATUS_FIELD: CONTACT_STATUS_CANDIDATE},
                )
                pipedrive_person_id = pd_person.get("id")
        except Exception as e:
            # Pipedrive is best-effort — never block saving the candidate locally.
            logger.warning(f"Pipedrive create_person failed for Pandius candidate: {e}")

        contact_result = await supabase.table("contacts").insert({
            "pipedrive_person_id": pipedrive_person_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "contact_status": "candidate",  # מועמד לחברה (canonical local value)
            "pipedrive_last_synced_at": "now()" if pipedrive_person_id else None,
        }).execute()

        if not contact_result.data:
            return {"status": "error", "message": "סליחה, בעיה בשמירת הפרטים."}

        contact_id = contact_result.data[0]["id"]
        await _link_contact(supabase, pandius_client_id, contact_id, full_name, email)

        logger.info(
            "pandius_candidate_saved",
            contact_id=contact_id,
            pandius_client_id=str(pandius_client_id),
        )
        return {
            "status": "success",
            "contact_id": contact_id,
            "message": "שמרתי את הפרטים שלך במערכת ✅",
        }
    except Exception as e:
        logger.error(f"save_candidate failed: {e}", exc_info=True)
        return {"status": "error", "message": "סליחה, בעיה בשמירת הפרטים."}


async def _link_contact(supabase, pandius_client_id, contact_id, full_name, email) -> None:
    """Attach the created/found contact to the pandius_client and mark intake done."""
    try:
        await supabase.table("pandius_clients").update({
            "contact_id": contact_id,
            "identified_at": "now()",
            "identification_method": "manual_intake_via_bot",
            "intake_status": "completed",
            "intake_collected_data": {"name": full_name, "email": email},
            "updated_at": "now()",
        }).eq("id", str(pandius_client_id)).execute()
    except Exception as e:
        logger.warning(f"Failed to link contact to pandius_client: {e}")


async def handle_search_open_jobs(
    conversation_id: UUID,
    pandius_client_id: UUID,
    query: str,
    limit: int = 8,
) -> dict[str, Any]:
    """Return a short list of currently-open positions for the LLM to match
    against the candidate. The LLM decides relevance and how to present them."""
    try:
        supabase = await get_supabase_client()
        res = await supabase.table("jobs").select("*").eq(
            "status", "open"
        ).limit(max(1, min(limit, 25))).execute()

        jobs = []
        for j in (res.data or []):
            jobs.append({
                "id": j.get("id"),
                "title": j.get("job_title") or j.get("title") or "משרה",
                "location": j.get("location") or j.get("job_location"),
                "clearance": j.get("job_security_clearance"),
                "summary": (j.get("job_description") or "")[:300],
            })

        if not jobs:
            return {
                "status": "no_jobs",
                "jobs": [],
                "message": "אין כרגע משרות פתוחות במאגר שמתאימות.",
            }
        return {"status": "success", "jobs": jobs, "total": len(jobs)}
    except Exception as e:
        logger.error(f"search_open_jobs failed: {e}", exc_info=True)
        return {"status": "error", "jobs": [], "message": "סליחה, בעיה בחיפוש המשרות."}


async def handle_transfer_to_recruitment(
    conversation_id: UUID,
    pandius_client_id: UUID,
    summary: str,
) -> dict[str, Any]:
    """Mark the conversation as handed off to the human recruitment team."""
    try:
        supabase = await get_supabase_client()
        await supabase.table("pandius_conversations").update(
            {"status": "transferred_to_recruitment", "summary": summary}
        ).eq("id", str(conversation_id)).execute()
        return {
            "status": "success",
            "message": "העברתי את הפנייה שלך לצוות הגיוס שלנו — הם יחזרו אליך. 🤝",
        }
    except Exception as e:
        logger.error(f"transfer_to_recruitment failed: {e}", exc_info=True)
        return {"status": "error", "message": "סליחה, בעיה בהעברה לצוות."}


TOOL_HANDLERS = {
    "identify_candidate": handle_identify_candidate,
    "save_candidate": handle_save_candidate,
    "search_open_jobs": handle_search_open_jobs,
    "transfer_to_recruitment": handle_transfer_to_recruitment,
}


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    conversation_id: UUID,
    pandius_client_id: UUID,
    phone: Optional[str] = None,
) -> dict[str, Any]:
    """Dispatch a tool call by name.

    ``phone`` is the candidate's real WhatsApp number, injected server-side. For
    phone-bearing tools we OVERRIDE whatever the model passed (it doesn't know
    the number and used to guess it, matching the wrong contact)."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        logger.error(f"Unknown Pandius tool: {tool_name}")
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}
    tool_input = dict(tool_input or {})
    if tool_name in ("identify_candidate", "save_candidate") and phone:
        tool_input["phone"] = phone
    try:
        return await handler(
            conversation_id=conversation_id,
            pandius_client_id=pandius_client_id,
            **tool_input,
        )
    except Exception as e:
        logger.error(f"Pandius tool {tool_name} failed: {e}", exc_info=True)
        return {"status": "error", "message": "סליחה, בעיה בביצוע הפעולה."}
