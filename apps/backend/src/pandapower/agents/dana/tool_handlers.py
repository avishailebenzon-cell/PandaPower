"""Dana tool handlers — execute the tools Dana's LLM calls."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from uuid import UUID

import structlog

from pandapower.core.supabase import get_supabase_client
from . import pipedrive_writer as pw

logger = structlog.get_logger(__name__)

# Fields that must be present (non-empty) before a deal can be created.
# job_security_clearance is intentionally NOT required.
REQUIRED_FIELDS = [
    "pipeline",
    "job_title",
    "job_description",
    "job_qualifications",
    "job_location",
    "deadline",
    "organization",
    "person",
    "person_phone",
    "person_link",
]

FIELD_LABELS_HE = {
    "pipeline": "פייפליין",
    "job_title": "כותרת המשרה",
    "job_description": "תיאור המשרה",
    "job_qualifications": "דרישות התפקיד",
    "job_location": "מיקום",
    "deadline": "מועד יעד",
    "organization": "שם הארגון",
    "person": "שם איש הקשר",
    "person_phone": "טלפון איש הקשר",
    "person_link": "חיבור איש הקשר ללקוח",
}


async def _load_context(conversation_id: UUID, supabase) -> Dict[str, Any]:
    res = await supabase.table("dana_conversations").select("job_context").eq(
        "id", str(conversation_id)
    ).single().execute()
    return (res.data or {}).get("job_context") or {}


async def _save_context(conversation_id: UUID, ctx: Dict[str, Any], supabase) -> None:
    await supabase.table("dana_conversations").update(
        {"job_context": ctx, "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", str(conversation_id)).execute()


async def handle_update_job_context(
    conversation_id: UUID, tool_input: Dict[str, Any], supabase
) -> Dict[str, Any]:
    ctx = await _load_context(conversation_id, supabase)
    updated = []
    for key, value in tool_input.items():
        if value not in (None, ""):
            ctx[key] = value
            updated.append(FIELD_LABELS_HE.get(key, key))
    await _save_context(conversation_id, ctx, supabase)

    missing = [FIELD_LABELS_HE[f] for f in REQUIRED_FIELDS if not ctx.get(f)]
    return {
        "status": "success",
        "updated_fields": updated,
        "missing_required": missing,
        "message": "",  # Dana phrases the user-facing reply herself
    }


async def handle_lookup_organization(
    tool_input: Dict[str, Any], supabase=None
) -> Dict[str, Any]:
    name = tool_input.get("name", "")
    client = pw.get_pipedrive_client()
    try:
        match = await pw.find_organization(client, name)
    finally:
        await client.close()
    if match:
        return {
            "status": "found",
            "match": match,
            "message": f"נמצא ארגון קיים תואם: {match['name']} (#{match['id']}).",
        }
    return {"status": "not_found", "message": f"לא נמצא ארגון קיים בשם '{name}'."}


async def handle_lookup_person(
    tool_input: Dict[str, Any], supabase=None
) -> Dict[str, Any]:
    name = tool_input.get("name", "")
    client = pw.get_pipedrive_client()
    try:
        match = await pw.find_person(client, name)
    finally:
        await client.close()
    if match:
        return {
            "status": "found",
            "match": match,
            "message": f"נמצא איש קשר קיים תואם: {match['name']} (#{match['id']}).",
        }
    return {"status": "not_found", "message": f"לא נמצא איש קשר קיים בשם '{name}'."}


async def handle_create_deal(
    conversation_id: UUID, tool_input: Dict[str, Any], supabase
) -> Dict[str, Any]:
    if not tool_input.get("confirm"):
        return {"status": "error", "message": "יצירת הדיל לא אושרה."}

    ctx = await _load_context(conversation_id, supabase)
    missing = [FIELD_LABELS_HE[f] for f in REQUIRED_FIELDS if not ctx.get(f)]
    if missing:
        return {
            "status": "error",
            "message": "חסרים פרטים לפני פתיחת הדיל: " + ", ".join(missing),
            "missing_required": missing,
        }

    # 1. Create in Pipedrive (find-or-create org + person, open deal).
    result = await pw.create_job_deal(ctx)
    if result.get("status") != "success":
        return result

    deal_id = result["deal_id"]

    # 2. Sync straight into the local jobs table so the role is immediately
    #    available for matching (no wait for the periodic Pipedrive sync).
    try:
        from pandapower.workers.pipedrive_deals_sync import _sync_deal

        deal_data = {
            "pipedrive_deal_id": deal_id,
            "job_title": ctx.get("job_title"),
            "job_description": ctx.get("job_description") or "",
            "job_qualifications": ctx.get("job_qualifications"),
            "job_location": ctx.get("job_location"),
            "job_security_clearance": ctx.get("job_security_clearance"),
            "deadline": ctx.get("deadline"),
            "person_id": result.get("person_id"),
            "org_id": result.get("org_id"),
            "status": "open",
            "contact_person_name": ctx.get("person"),
            "organization_name": ctx.get("organization"),
            "pipedrive_last_synced_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        await _sync_deal(supabase, deal_data)
        result["notes"].append("הדיל סונכרן למערכת PandaPower וזמין לגיוס.")
    except Exception as e:
        logger.error("dana_local_job_sync_failed", error=str(e), deal_id=deal_id)
        result["notes"].append(
            "הדיל נוצר בפייפדרייב, אך הסנכרון האוטומטי למערכת ייעשה בסבב הסנכרון הבא."
        )

    # 3. Mark the conversation done.
    await supabase.table("dana_conversations").update(
        {
            "status": "deal_created",
            "pipedrive_deal_id": deal_id,
            "updated_at": datetime.utcnow().isoformat(),
        }
    ).eq("id", str(conversation_id)).execute()

    return {
        "status": "success",
        "deal_id": deal_id,
        "message": "✅ " + " ".join(result.get("notes", [])),
    }


async def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    conversation_id: UUID,
    supabase=None,
) -> Dict[str, Any]:
    """Dispatch a tool call to its handler."""
    if supabase is None:
        supabase = await get_supabase_client()
    try:
        if tool_name == "update_job_context":
            return await handle_update_job_context(conversation_id, tool_input, supabase)
        if tool_name == "lookup_organization":
            return await handle_lookup_organization(tool_input, supabase)
        if tool_name == "lookup_person":
            return await handle_lookup_person(tool_input, supabase)
        if tool_name == "create_deal":
            return await handle_create_deal(conversation_id, tool_input, supabase)
        return {"status": "error", "message": f"כלי לא מוכר: {tool_name}"}
    except Exception as e:
        logger.error("dana_tool_failed", tool=tool_name, error=str(e))
        return {"status": "error", "message": f"שגיאה בהרצת הכלי {tool_name}: {e}"}
