"""Handle incoming Pandius messages from the Green API webhook.

Pandius is inbound-only. Each incoming WhatsApp message (text or a CV file) is
routed here: we identify/create the pandius_client, persist the message, ingest
any attached CV into the scan pipeline, and let Pandius's engine reply.
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID

from pandapower.workers.celery_app import app
from pandapower.core.supabase import get_supabase_client
from pandapower.core.phone import to_international
from .conversation_handler import handle_candidate_message
from .cv_ingest import ingest_whatsapp_cv

logger = logging.getLogger(__name__)


async def _get_or_create_client(supabase, phone: str, chat_id: str) -> dict | None:
    res = await supabase.table("pandius_clients").select("*").eq(
        "phone", phone
    ).limit(1).execute()
    if res.data:
        await supabase.table("pandius_clients").update({
            "last_message_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", res.data[0]["id"]).execute()
        return res.data[0]

    created = await supabase.table("pandius_clients").insert({
        "phone": phone,
        "whatsapp_chat_id": chat_id or f"{phone.replace('+', '')}@c.us",
        "intake_status": "in_progress",
        "identification_method": "manual_intake_via_bot",
        "first_message_at": datetime.utcnow().isoformat(),
        "last_message_at": datetime.utcnow().isoformat(),
    }).execute()
    return created.data[0] if created.data else None


async def _get_or_create_conversation(supabase, client_id: str) -> dict | None:
    res = await supabase.table("pandius_conversations").select("*").eq(
        "pandius_client_id", client_id
    ).eq("status", "open").order("started_at", desc=True).limit(1).execute()
    if res.data:
        return res.data[0]
    created = await supabase.table("pandius_conversations").insert({
        "pandius_client_id": client_id,
        "status": "open",
        "started_at": datetime.utcnow().isoformat(),
        "last_activity_at": datetime.utcnow().isoformat(),
    }).execute()
    return created.data[0] if created.data else None


async def _process_pandius_incoming_message_async(payload: dict) -> dict:
    try:
        supabase = await get_supabase_client()

        messages = payload.get("messages", [])
        if not messages:
            return {"status": "skipped", "reason": "No messages in payload"}
        message = messages[0]

        green_api_message_id = message.get("id")
        chat_id = message.get("from", "")
        phone = chat_id.replace("@c.us", "")
        message_text = message.get("text", "") or ""
        message_type = message.get("message_type", "text")
        timestamp = message.get("timestamp", int(datetime.utcnow().timestamp()))

        if not phone:
            return {"status": "failed", "reason": "No sender phone"}

        # Idempotency.
        if green_api_message_id:
            dup = await supabase.table("pandius_messages").select("id").eq(
                "green_api_message_id", green_api_message_id
            ).limit(1).execute()
            if dup.data:
                return {"status": "skipped", "reason": "Duplicate message"}

        client = await _get_or_create_client(supabase, phone, chat_id)
        if not client:
            return {"status": "failed", "reason": "Could not create client"}
        client_id = client["id"]

        conv = await _get_or_create_conversation(supabase, client_id)
        if not conv:
            return {"status": "failed", "reason": "Could not create conversation"}
        conversation_id = conv["id"]

        is_document = message_type in ("document", "image") and message.get("download_url")

        # Persist the inbound message.
        await supabase.table("pandius_messages").insert({
            "conversation_id": conversation_id,
            "pandius_client_id": client_id,
            "direction": "inbound",
            "message_type": "document" if is_document else "text",
            "green_api_message_id": green_api_message_id,
            "text": message_text or (message.get("filename") if is_document else ""),
            "document_url": message.get("download_url") if is_document else None,
            "document_filename": message.get("filename") if is_document else None,
            "sent_at": datetime.fromtimestamp(timestamp).isoformat(),
        }).execute()

        # Human takeover — store the message but don't let Pandius reply.
        if conv.get("auto_reply_paused"):
            return {"status": "paused", "client_id": client_id}

        # CV file: ingest into the scan pipeline, then let Pandius acknowledge.
        if is_document:
            cv_id = await ingest_whatsapp_cv(
                supabase,
                download_url=message.get("download_url"),
                filename=message.get("filename") or "cv.pdf",
                mime_type=message.get("mime_type") or "application/pdf",
                phone=phone,
                green_api_message_id=green_api_message_id,
                pandius_client_id=client_id,
            )
            if cv_id:
                try:
                    await supabase.table("pandius_clients").update({
                        "cv_received_at": datetime.utcnow().isoformat(),
                        "cv_file_id": cv_id,
                        "updated_at": datetime.utcnow().isoformat(),
                    }).eq("id", client_id).execute()
                except Exception:
                    pass
            # Synthetic prompt so Pandius reacts to the CV and moves forward.
            incoming_for_engine = (
                "(המועמד שלח עכשיו קובץ קורות חיים — הוא נקלט במערכת. "
                "תודה לו בקצרה, ונסה למצוא משרה מתאימה.)"
            )
        else:
            incoming_for_engine = message_text

        if not incoming_for_engine.strip():
            return {"status": "processed", "client_id": client_id}

        result = await handle_candidate_message(
            conversation_id=UUID(str(conversation_id)),
            pandius_client_id=UUID(str(client_id)),
            incoming_text=incoming_for_engine,
            chat_id=chat_id or f"{phone.replace('+', '')}@c.us",
            # Canonical international digits (e.g. "972586665248") — injected into
            # the tool calls so the model never has to know/guess the phone.
            phone=to_international(phone) or phone,
        )
        return {"status": "processed", "client_id": client_id, "reply": result}

    except Exception as e:
        logger.error(f"Failed to process Pandius message: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def process_pandius_incoming_message(self, payload: dict) -> dict:
    """Celery task: process one Pandius webhook message."""
    logger.info("Processing incoming Pandius message")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                _process_pandius_incoming_message_async(payload)
            )
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Pandius message task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
