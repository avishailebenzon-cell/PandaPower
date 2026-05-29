"""Webhook receivers for external integrations.

Per-agent Green-API webhooks live under /webhooks/whatsapp/{agent_code}.
Each of the 3 WhatsApp agents (Tal, Elad, Pandi) has its own dedicated
endpoint, isolated by URL path and by per-agent webhook_secret stored
in system_settings.

Endpoint shape (POST):
    /webhooks/whatsapp/tal
    /webhooks/whatsapp/elad
    /webhooks/whatsapp/pandi

Auth options Green API will use to call us — any of:
    1. ?token=<webhook_secret> query parameter
    2. Authorization: Bearer <webhook_secret> header
If the agent's webhook_secret is empty in system_settings we accept
without verifying (warn-log only) — this lets you start collecting events
before locking down auth.

The endpoint:
  • Always responds 200 quickly so Green API never retries on us.
  • Records inbound messages into pandi_messages (defensively — the prod
    schema is narrower than the migration so we degrade gracefully if a
    column / table is missing).
  • Logs the event type + sender for observability.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Depends

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


SUPPORTED_AGENTS = {"tal", "elad", "pandi"}


async def _get_webhook_secret(supabase, agent_code: str) -> str:
    """Read this agent's webhook_secret from system_settings, or ''."""
    try:
        resp = await (
            supabase.table("system_settings")
            .select("setting_value")
            .eq("setting_key", f"{agent_code}.webhook_secret")
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return (rows[0].get("setting_value") if rows else "") or ""
    except Exception as e:
        logger.warning(f"Could not load webhook_secret for {agent_code}: {e}")
        return ""


def _verify_secret(expected: str, provided: Optional[str]) -> bool:
    """Empty `expected` means "no auth configured yet" — accept everything.

    Otherwise require an exact match (case-sensitive). HMAC isn't necessary
    here because Green API itself doesn't sign payloads — it just appends
    the bearer token / query param the user supplied at instance config.
    """
    if not expected:
        return True
    return bool(provided) and provided == expected


def _extract_provided_secret(request: Request) -> Optional[str]:
    """Pull the secret from either the query string or Authorization header."""
    q = request.query_params.get("token")
    if q:
        return q
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(None, 1)[1].strip()
    return None


def _normalise_green_api_payload(payload: dict) -> dict:
    """Turn Green API's webhook payload into the few fields we actually store.

    Green API event examples we handle:
      • typeWebhook="incomingMessageReceived"
        + messageData.typeMessage="textMessage" / "extendedTextMessage"
        + senderData.chatId / senderName
      • typeWebhook="outgoingMessageStatus"
      • typeWebhook="stateInstanceChanged"
    Anything we don't recognise is logged but acknowledged.
    """
    event_type = payload.get("typeWebhook") or payload.get("eventType") or "unknown"
    sender_data = payload.get("senderData") or {}
    message_data = payload.get("messageData") or {}

    text: Optional[str] = None
    msg_type = message_data.get("typeMessage") or "text"
    if msg_type == "textMessage":
        text = (message_data.get("textMessageData") or {}).get("textMessage")
    elif msg_type == "extendedTextMessage":
        text = (message_data.get("extendedTextMessageData") or {}).get("text")

    return {
        "event_type": event_type,
        "green_api_message_id": payload.get("idMessage"),
        "from_chat_id": sender_data.get("chatId"),
        "from_phone": (sender_data.get("chatId") or "").split("@")[0] or None,
        "sender_name": sender_data.get("senderName"),
        "text": text,
        "message_type": msg_type,
        "timestamp": payload.get("timestamp"),
    }


async def _log_inbound_message(supabase, agent_code: str, parsed: dict) -> None:
    """Best-effort write to pandi_messages. Never raises — webhooks must reply 200.

    The deployed pandi_messages table is missing several columns the migration
    defined (notably bot_code, the LLM-token fields). We attempt the richest
    write first, drop fields on schema errors, and skip entirely if the table
    is absent.
    """
    if parsed.get("event_type") != "incomingMessageReceived":
        return
    if not parsed.get("text"):
        return

    row = {
        "direction": "inbound",
        "message_type": parsed.get("message_type", "text"),
        "text": parsed.get("text"),
        "green_api_message_id": parsed.get("green_api_message_id"),
        "bot_code": agent_code,           # may not exist in schema yet — fallback below
        "from_phone": parsed.get("from_phone"),
        "created_at": datetime.utcnow().isoformat(),
    }

    # Try the rich insert, then progressively drop "exotic" columns. We can't
    # cover every missing-column case but each attempt is a smaller payload.
    for keys_to_drop in ([], ["bot_code"], ["bot_code", "from_phone"], ["bot_code", "from_phone", "green_api_message_id"]):
        attempt = {k: v for k, v in row.items() if k not in keys_to_drop}
        try:
            await supabase.table("pandi_messages").insert(attempt).execute()
            return
        except Exception as e:
            msg = str(e)[:200]
            if "does not exist" in msg or "schema cache" in msg or "PGRST204" in msg:
                continue  # try a smaller payload
            logger.warning(f"Insert into pandi_messages failed for {agent_code}: {msg}")
            return
    logger.info(f"pandi_messages table unavailable — skipping persistence for {agent_code} event")


@router.post("/whatsapp/{agent_code}")
async def receive_whatsapp_webhook(
    agent_code: str,
    request: Request,
    supabase=Depends(get_supabase_client),
) -> dict[str, Any]:
    """One endpoint, per-agent isolation via the URL path.

    Always returns 200 (even on internal error) so Green API stops retrying.
    Auth failures are the one exception — those return 401 so the operator
    notices misconfiguration.
    """
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")

    # Read raw body once — Green API sends JSON
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    # Auth
    expected = await _get_webhook_secret(supabase, agent_code)
    provided = _extract_provided_secret(request)
    if not _verify_secret(expected, provided):
        logger.warning(f"Webhook auth failed for agent={agent_code}")
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    parsed = _normalise_green_api_payload(payload) if isinstance(payload, dict) else {}
    logger.info(
        "WhatsApp webhook | agent=%s event=%s msg_id=%s from=%s text_len=%s",
        agent_code,
        parsed.get("event_type"),
        parsed.get("green_api_message_id"),
        parsed.get("from_phone"),
        len(parsed.get("text") or ""),
    )

    # Best-effort persistence (won't raise)
    try:
        await _log_inbound_message(supabase, agent_code, parsed)
    except Exception as e:
        logger.warning(f"Webhook logging failed for {agent_code}: {e}")

    # Enqueue Celery task to process the message (Session 34)
    if agent_code == "pandi" and parsed.get("event_type") == "incomingMessageReceived" and parsed.get("text"):
        try:
            from pandapower.workers.pandi.message_handler import process_pandi_incoming_message

            # Convert parsed fields back to Green API format for message_handler
            celery_payload = {
                "messages": [{
                    "id": parsed.get("green_api_message_id"),
                    "from": parsed.get("from_chat_id"),
                    "text": parsed.get("text"),
                    "timestamp": parsed.get("timestamp", int(datetime.now().timestamp())),
                }]
            }

            # Enqueue async task
            task = process_pandi_incoming_message.delay(celery_payload)
            logger.info(f"Enqueued Celery task {task.id} for Pandi message processing")
        except Exception as e:
            logger.error(f"Failed to enqueue Pandi message task: {e}", exc_info=True)

    return {"status": "ok", "agent": agent_code, "event": parsed.get("event_type")}
