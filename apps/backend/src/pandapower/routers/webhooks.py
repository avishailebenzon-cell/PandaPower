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

import asyncio
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


async def _find_recruiter_conversation_for_phone(
    supabase, recruiter: str, phone: str
) -> Optional[str]:
    """Locate the recruiter conversation a given phone belongs to.

    First tries the cached candidate_phone column, then falls back to matching
    the candidate by phone and finding their most recent conversation for this
    recruiter. Returns the conversation id (uuid str) or None.
    """
    from pandapower.agents.recruiter_chat.engine import normalize_phone

    digits = normalize_phone(phone)
    if not digits:
        return None

    # 1) Cached candidate_phone on the conversation.
    try:
        res = await (
            supabase.table("recruiter_conversations")
            .select("id, updated_at")
            .eq("recruiter", recruiter)
            .eq("candidate_phone", digits)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]["id"]
    except Exception as e:
        logger.warning(f"{recruiter} conv lookup by cached phone failed: {e}")

    # 2) Fallback: find candidate(s) by phone, then their conversation.
    try:
        cand_res = await supabase.table("candidates").select("id, phone").execute()
        candidate_ids = [
            c["id"] for c in (cand_res.data or [])
            if normalize_phone(c.get("phone")).endswith(digits[-9:])
            or digits.endswith(normalize_phone(c.get("phone"))[-9:] if c.get("phone") else "")
        ]
        if not candidate_ids:
            return None
        match_res = await (
            supabase.table("matches")
            .select("id")
            .in_("candidate_id", candidate_ids)
            .execute()
        )
        match_ids = [m["id"] for m in (match_res.data or [])]
        if not match_ids:
            return None
        conv_res = await (
            supabase.table("recruiter_conversations")
            .select("id, updated_at")
            .eq("recruiter", recruiter)
            .in_("match_id", match_ids)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if conv_res.data:
            conv_id = conv_res.data[0]["id"]
            # Cache the phone for fast routing next time.
            try:
                await supabase.table("recruiter_conversations").update(
                    {"candidate_phone": digits}
                ).eq("id", conv_id).execute()
            except Exception:
                pass
            return conv_id
    except Exception as e:
        logger.warning(f"{recruiter} conv lookup by candidate phone failed: {e}")
    return None


async def _handle_recruiter_inbound(recruiter: str, parsed: dict) -> None:
    """Record an inbound message for a recruiter (tal/elad) and auto-reply if
    the conversation isn't paused."""
    from uuid import UUID
    from pandapower.agents.recruiter_chat.engine import RecruiterChatEngine

    try:
        supabase = await get_supabase_client()
        phone = parsed.get("from_phone") or ""
        conv_id = await _find_recruiter_conversation_for_phone(supabase, recruiter, phone)
        if not conv_id:
            logger.info(f"{recruiter} inbound: no conversation matched phone={phone}; dropping")
            return

        engine = RecruiterChatEngine(recruiter)
        await engine.record_inbound(UUID(conv_id), parsed["text"])
        # Auto-reply (the engine itself skips if the conversation is paused).
        await engine.generate_reply(UUID(conv_id))
    except Exception as e:
        logger.error(f"{recruiter} inbound handling failed: {e}", exc_info=True)


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

    # Tal/Elad: route the inbound message into the recruiter conversation and
    # let the agent auto-reply (unless a human has paused it). Done in the
    # background so we return 200 immediately and Green API never retries.
    if agent_code in ("tal", "elad") and parsed.get("event_type") == "incomingMessageReceived" and parsed.get("text"):
        try:
            asyncio.create_task(_handle_recruiter_inbound(agent_code, parsed))
        except Exception as e:
            logger.error(f"Failed to spawn {agent_code} inbound handler: {e}", exc_info=True)

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


# ===========================================================================
# Telegram bot — "מנהל גיוס כרמית" (read-only conversational assistant)
# ===========================================================================

CARMIT_SYSTEM_PROMPT = (
    "את כרמית, מנהלת הגיוס הראשית של מערכת PandaPower (גיוס טכנולוגי/ביטחוני). "
    "את משוחחת עם אבישי, מנהל המערכת, דרך טלגרם. עני בעברית, בקצרה, בחום ובמקצועיות. "
    "יש לך גישה לנתוני המערכת בזמן אמת (מצורפים למטה תחת 'נתוני מערכת נוכחיים'). "
    "ענֵי אך ורק על סמך הנתונים האלה; אם חסר מידע — אמרי בכנות שאינך יודעת, ואל תמציאי מספרים. "
    "את במצב קריאה-בלבד: אינך יכולה לבצע פעולות (לאשר/לדחות/להריץ), רק לדווח, להסביר ולנתח. "
    "אם מבקשים ממך לבצע פעולה — הסבירי בעדינות שיש לעשות זאת בממשק המערכת."
)


async def _build_carmit_snapshot(sb) -> str:
    """Compact, real-time system snapshot injected into Carmit's context."""
    lines: list[str] = []
    # Scheduler health
    try:
        from pandapower.routers.admin.health import scheduler_heartbeat
        hb = await scheduler_heartbeat()
        lines.append(f"בריאות תהליכים: {hb.overall_status} — {hb.summary}")
        stalled = [t.label for t in hb.tasks if t.is_stalled]
        if stalled:
            lines.append("תהליכים תקועים: " + ", ".join(stalled))
    except Exception as e:
        logger.debug(f"[telegram] snapshot heartbeat failed: {e}")

    # Pipeline state counts
    try:
        from pandapower.routers.admin.health import pipeline_status
        ps = await pipeline_status()
        lines.append(f"סך-הכל התאמות פעילות במערכת: {ps.total_matches}")
        nonzero = [f"{s.stage_label}: {s.count}" for s in ps.stages if s.count]
        if nonzero:
            lines.append("פילוח לפי שלב — " + "; ".join(nonzero))
        if ps.bottleneck:
            lines.append(f"צוואר בקבוק: {ps.bottleneck}")
    except Exception as e:
        logger.debug(f"[telegram] snapshot pipeline failed: {e}")

    # Email intake totals
    try:
        total = await sb.table("email_intake_log").select("id", count="exact").execute()
        lines.append(f"סך-הכל מיילים שעובדו: {getattr(total, 'count', 0) or 0}")
    except Exception:
        pass

    return "\n".join(lines) if lines else "אין נתונים זמינים כרגע."


async def _handle_carmit_message(text: str, chat_id: str) -> None:
    """Answer one admin message as Carmit (runs in the background)."""
    from pandapower.core.config import settings
    from pandapower.integrations.claude_api import AnthropicClient
    from pandapower.integrations.telegram_client import TelegramClient, get_telegram_config

    sb = await get_supabase_client()
    cfg = await get_telegram_config(sb)
    token = cfg.get("bot_token")
    if not token:
        return

    tg = TelegramClient(token)
    try:
        if not settings.ANTHROPIC_API_KEY:
            await tg.send_message(chat_id, "מצטערת, חסר מפתח Claude בהגדרות — לא אוכל לענות כרגע.")
            return

        snapshot = await _build_carmit_snapshot(sb)
        system = f"{CARMIT_SYSTEM_PROMPT}\n\n--- נתוני מערכת נוכחיים ---\n{snapshot}"
        claude = AnthropicClient(settings.ANTHROPIC_API_KEY)
        try:
            resp = await claude._make_request_with_retry(
                messages=[{"role": "user", "content": text}],
                system=system,
            )
            answer = (resp.get("content") or [{}])[0].get("text") or "לא הצלחתי לנסח תשובה."
        finally:
            await claude.close()

        await tg.send_message(chat_id, answer)
    except Exception as e:
        logger.error(f"[telegram] Carmit reply failed: {e}", exc_info=True)
        try:
            await tg.send_message(chat_id, "אירעה שגיאה זמנית. נסה שוב בעוד רגע 🙏")
        except Exception:
            pass
    finally:
        await tg.close()


@router.post("/telegram")
async def receive_telegram_webhook(
    request: Request,
    supabase=Depends(get_supabase_client),
) -> dict[str, Any]:
    """Telegram bot webhook. Verifies the secret header, binds the admin chat on
    /start, and answers admin messages as Carmit (read-only). Always returns 200
    quickly (heavy work is spawned in the background)."""
    from pandapower.integrations.telegram_client import get_telegram_config, TelegramClient

    cfg = await get_telegram_config(supabase)

    # Verify Telegram's secret-token header (reuse the optional-secret pattern).
    expected = cfg.get("webhook_secret") or ""
    provided = request.headers.get("x-telegram-bot-api-secret-token")
    if expected and provided != expected:
        logger.warning("[telegram] webhook auth failed")
        raise HTTPException(status_code=401, detail="Invalid secret token")

    try:
        update = await request.json()
    except Exception:
        return {"status": "ok"}

    message = (update or {}).get("message") or (update or {}).get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text:
        return {"status": "ok"}
    chat_id = str(chat_id)

    token = cfg.get("bot_token")
    admin_chat_id = cfg.get("admin_chat_id")

    # /start binds the admin chat (first sender wins) and greets.
    if text.startswith("/start"):
        if not admin_chat_id:
            try:
                await supabase.table("system_settings").upsert(
                    {"setting_key": "telegram.admin_chat_id", "setting_value": chat_id,
                     "updated_at": datetime.utcnow().isoformat()},
                    on_conflict="setting_key",
                ).execute()
                admin_chat_id = chat_id
            except Exception as e:
                logger.error(f"[telegram] failed to store admin_chat_id: {e}")
        if token:
            tg = TelegramClient(token)
            try:
                if admin_chat_id == chat_id:
                    await tg.send_message(chat_id, (
                        "שלום! אני כרמית, מנהלת הגיוס 🤖\n"
                        "אפשר לשאול אותי על מצב המערכת, ההתאמות, התהליכים ובעיות. "
                        "אדווח לך גם כשהתאמה עוברת לטל, על גיוסים, ועל תקלות בתהליכים.\n\n"
                        "נסה: \"מה מצב המערכת?\""
                    ))
                else:
                    await tg.send_message(chat_id, "הבוט כבר משויך למנהל אחר.")
            finally:
                await tg.close()
        return {"status": "ok"}

    # Only the bound admin may converse. Ignore everyone else silently.
    if not admin_chat_id or chat_id != str(admin_chat_id):
        logger.info(f"[telegram] ignoring message from non-admin chat {chat_id}")
        return {"status": "ok"}

    # Answer in the background so we return 200 immediately (no Telegram retry).
    asyncio.create_task(_handle_carmit_message(text, chat_id))
    return {"status": "ok"}
