"""WhatsApp-style conversations screen for Pandi (client-intake agent).

Same UX as Tal/Elad, but over Pandi's own tables (pandi_conversations /
pandi_messages / pandi_clients) and her existing conversation engine:
  GET  /admin/pandi-chat/conversations                 — list (newest first)
  GET  /admin/pandi-chat/conversations/{id}            — detail + messages
  POST /admin/pandi-chat/conversations/{id}/send       — operator writes AS Pandi
  POST /admin/pandi-chat/conversations/{id}/pause      — toggle AI auto-reply
  POST /admin/pandi-chat/conversations/{id}/generate   — trigger Pandi's reply now

Pandi's normal auto-reply runs through the Green-API webhook → Celery pipeline
(workers/pandi/message_handler.py), which honours the same auto_reply_paused
flag this screen toggles.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/pandi-chat", tags=["admin", "pandi", "chat"])


class ConversationSummary(BaseModel):
    id: str
    candidate_name: str = "לקוח"  # the client's display name (reuses the shared UI field)
    job_title: str = ""           # job context title, if any
    status: str = "open"
    auto_reply_paused: bool = False
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None
    started_at: Optional[str] = None


class ChatMessage(BaseModel):
    id: str
    direction: str  # inbound | outbound
    text: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None


class ConversationDetail(BaseModel):
    id: str
    candidate_name: str = "לקוח"
    job_title: str = ""
    status: str = "open"
    auto_reply_paused: bool = False
    messages: List[ChatMessage] = []


class SendMessageRequest(BaseModel):
    text: str


class SendMessageResponse(BaseModel):
    text: str
    delivered: bool


class PauseRequest(BaseModel):
    paused: bool


class PauseResponse(BaseModel):
    auto_reply_paused: bool


def _client_name(client: dict) -> str:
    if not isinstance(client, dict):
        return "לקוח"
    collected = client.get("intake_collected_data") or {}
    if isinstance(collected, dict):
        name = collected.get("name") or collected.get("company")
        if name:
            return str(name)
    return client.get("phone") or "לקוח"


def _job_title(conv: dict) -> str:
    ctx = conv.get("job_context") or {}
    if isinstance(ctx, dict) and ctx.get("title"):
        return str(ctx["title"])
    return ""


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_pandi_conversations(limit: int = 100, supabase=Depends(get_supabase_client)):
    try:
        res = await supabase.table("pandi_conversations").select(
            "id, status, auto_reply_paused, started_at, last_activity_at, job_context, "
            "pandi_clients(phone, intake_collected_data)"
        ).order("last_activity_at", desc=True).limit(limit).execute()

        out: List[ConversationSummary] = []
        for conv in res.data or []:
            client = conv.get("pandi_clients") or {}
            last_text, last_at = None, None
            try:
                msg_res = await supabase.table("pandi_messages").select(
                    "text, sent_at"
                ).eq("conversation_id", conv["id"]).order(
                    "sent_at", desc=True
                ).limit(1).execute()
                if msg_res.data:
                    last_text = msg_res.data[0].get("text")
                    last_at = msg_res.data[0].get("sent_at")
            except Exception:
                pass

            out.append(ConversationSummary(
                id=conv["id"],
                candidate_name=_client_name(client),
                job_title=_job_title(conv),
                status=conv.get("status") or "open",
                auto_reply_paused=bool(conv.get("auto_reply_paused")),
                last_message=last_text,
                last_message_at=last_at,
                started_at=conv.get("started_at"),
            ))
        return out
    except Exception as e:
        logger.error(f"Pandi list_conversations failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_pandi_conversation(conversation_id: UUID, supabase=Depends(get_supabase_client)):
    try:
        res = await supabase.table("pandi_conversations").select(
            "id, status, auto_reply_paused, job_context, "
            "pandi_clients(phone, intake_collected_data)"
        ).eq("id", str(conversation_id)).limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv = res.data[0]
        client = conv.get("pandi_clients") or {}

        msg_res = await supabase.table("pandi_messages").select(
            "id, direction, text, sent_at"
        ).eq("conversation_id", str(conversation_id)).order(
            "sent_at", desc=False
        ).execute()
        messages = [
            ChatMessage(
                id=m["id"],
                direction=m.get("direction", "outbound"),
                text=m.get("text"),
                author=None,
                created_at=m.get("sent_at"),
            )
            for m in (msg_res.data or [])
        ]
        return ConversationDetail(
            id=conv["id"],
            candidate_name=_client_name(client),
            job_title=_job_title(conv),
            status=conv.get("status") or "open",
            auto_reply_paused=bool(conv.get("auto_reply_paused")),
            messages=messages,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandi get_conversation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


async def _load_conv_client(conversation_id: UUID, supabase) -> Optional[dict]:
    res = await supabase.table("pandi_conversations").select(
        "id, pandi_client_id, pandi_clients(whatsapp_chat_id, phone)"
    ).eq("id", str(conversation_id)).limit(1).execute()
    return res.data[0] if res.data else None


@router.post("/conversations/{conversation_id}/send", response_model=SendMessageResponse)
async def send_pandi_message(
    conversation_id: UUID, request: SendMessageRequest,
    supabase=Depends(get_supabase_client),
):
    """Operator writes a message AS Pandi: stored as an outbound pandi_message
    and delivered to the client via Pandi's Green-API instance. AI not invoked."""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Message text is required")
    text = request.text.strip()
    try:
        conv = await _load_conv_client(conversation_id, supabase)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        client = conv.get("pandi_clients") or {}

        await supabase.table("pandi_messages").insert({
            "conversation_id": str(conversation_id),
            "pandi_client_id": conv.get("pandi_client_id"),
            "direction": "outbound",
            "message_type": "text",
            "text": text,
            "sent_at": datetime.utcnow().isoformat(),
        }).execute()
        await supabase.table("pandi_conversations").update(
            {"last_activity_at": datetime.utcnow().isoformat()}
        ).eq("id", str(conversation_id)).execute()

        delivered = False
        chat_id = client.get("whatsapp_chat_id") or (
            f"{(client.get('phone') or '').replace('+', '')}@c.us" if client.get("phone") else None
        )
        if chat_id:
            try:
                from pandapower.integrations.green_api import get_green_api_client

                gclient = await get_green_api_client("pandi")
                if gclient:
                    result = await gclient.send_message(chat_id, text)
                    delivered = bool(result.get("success"))
                    await gclient.close()
            except Exception as send_err:
                logger.warning(f"Pandi WhatsApp send failed (message saved): {send_err}")

        return SendMessageResponse(text=text, delivered=delivered)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandi send_message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.post("/conversations/{conversation_id}/pause", response_model=PauseResponse)
async def set_pandi_pause(
    conversation_id: UUID, request: PauseRequest,
    supabase=Depends(get_supabase_client),
):
    try:
        res = await supabase.table("pandi_conversations").update({
            "auto_reply_paused": request.paused,
            "last_activity_at": datetime.utcnow().isoformat(),
        }).eq("id", str(conversation_id)).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return PauseResponse(auto_reply_paused=request.paused)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandi set_pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update pause state")


@router.post("/conversations/{conversation_id}/generate", response_model=SendMessageResponse)
async def generate_pandi_reply(conversation_id: UUID, supabase=Depends(get_supabase_client)):
    """Manually run Pandi's engine on the latest inbound message and send the
    reply (mirrors the live webhook pipeline). Useful for driving/testing."""
    try:
        conv = await _load_conv_client(conversation_id, supabase)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        client = conv.get("pandi_clients") or {}

        last_inbound = await supabase.table("pandi_messages").select(
            "text"
        ).eq("conversation_id", str(conversation_id)).eq(
            "direction", "inbound"
        ).order("sent_at", desc=True).limit(1).execute()
        if not last_inbound.data or not (last_inbound.data[0].get("text") or "").strip():
            return SendMessageResponse(text="", delivered=False)

        chat_id = client.get("whatsapp_chat_id") or (
            f"{(client.get('phone') or '').replace('+', '')}@c.us" if client.get("phone") else ""
        )
        from pandapower.workers.pandi.conversation_handler import handle_client_message

        result = await handle_client_message(
            conversation_id=conversation_id,
            pandi_client_id=UUID(str(conv["pandi_client_id"])),
            incoming_text=last_inbound.data[0]["text"],
            chat_id=chat_id or "",
        )
        return SendMessageResponse(
            text=(result or {}).get("response_text", "") if isinstance(result, dict) else "",
            delivered=(result or {}).get("status") == "sent" if isinstance(result, dict) else False,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandi generate_reply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate reply")
