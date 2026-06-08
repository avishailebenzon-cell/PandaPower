"""WhatsApp-style conversations screen for Pandius (candidate-intake agent).

Same UX as Tal/Elad/Pandi, over Pandius's own tables (pandius_conversations /
pandius_messages / pandius_clients) and his conversation engine:
  GET  /admin/pandius-chat/conversations               — list (newest first)
  GET  /admin/pandius-chat/conversations/{id}          — detail + messages
  POST /admin/pandius-chat/conversations/{id}/send     — operator writes AS Pandius
  POST /admin/pandius-chat/conversations/{id}/pause    — toggle AI auto-reply
  POST /admin/pandius-chat/conversations/{id}/close    — close / reopen
  POST /admin/pandius-chat/conversations/{id}/generate — trigger Pandius's reply now
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
router = APIRouter(prefix="/admin/pandius-chat", tags=["admin", "pandius", "chat"])


class ConversationSummary(BaseModel):
    id: str
    candidate_name: str = "מועמד"
    job_title: str = ""
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
    candidate_name: str = "מועמד"
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


class CloseRequest(BaseModel):
    closed: bool = True


class CloseResponse(BaseModel):
    status: str
    auto_reply_paused: bool


def _client_name(client: dict) -> str:
    if not isinstance(client, dict):
        return "מועמד"
    collected = client.get("intake_collected_data") or {}
    if isinstance(collected, dict) and collected.get("name"):
        return str(collected["name"])
    return client.get("phone") or "מועמד"


def _job_title(conv: dict) -> str:
    ctx = conv.get("candidate_context") or {}
    if isinstance(ctx, dict) and ctx.get("desired_role"):
        return str(ctx["desired_role"])
    return ""


async def _fetch_client(supabase, client_id) -> dict:
    if not client_id:
        return {}
    try:
        res = await supabase.table("pandius_clients").select("*").eq(
            "id", str(client_id)
        ).limit(1).execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


async def _list_conversations_rows(supabase, limit: int) -> list:
    for order_col in ("last_activity_at", "started_at", None):
        try:
            q = supabase.table("pandius_conversations").select("*").limit(limit)
            if order_col:
                q = q.order(order_col, desc=True)
            res = await q.execute()
            return res.data or []
        except Exception:
            continue
    return []


@router.get("/conversations", response_model=List[ConversationSummary])
async def list_pandius_conversations(limit: int = 100, supabase=Depends(get_supabase_client)):
    try:
        rows = await _list_conversations_rows(supabase, limit)
        out: List[ConversationSummary] = []
        for conv in rows:
            client = await _fetch_client(supabase, conv.get("pandius_client_id"))
            last_text, last_at = None, None
            try:
                msg_res = await supabase.table("pandius_messages").select(
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
        logger.error(f"Pandius list_conversations failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_pandius_conversation(conversation_id: UUID, supabase=Depends(get_supabase_client)):
    try:
        res = await supabase.table("pandius_conversations").select("*").eq(
            "id", str(conversation_id)
        ).limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv = res.data[0]
        client = await _fetch_client(supabase, conv.get("pandius_client_id"))

        msg_res = await supabase.table("pandius_messages").select("*").eq(
            "conversation_id", str(conversation_id)
        ).order("sent_at", desc=False).execute()
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
        logger.error(f"Pandius get_conversation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


async def _load_conv_client(conversation_id: UUID, supabase) -> Optional[dict]:
    res = await supabase.table("pandius_conversations").select("*").eq(
        "id", str(conversation_id)
    ).limit(1).execute()
    if not res.data:
        return None
    conv = res.data[0]
    conv["pandius_clients"] = await _fetch_client(supabase, conv.get("pandius_client_id"))
    return conv


@router.post("/conversations/{conversation_id}/send", response_model=SendMessageResponse)
async def send_pandius_message(
    conversation_id: UUID, request: SendMessageRequest,
    supabase=Depends(get_supabase_client),
):
    """Operator writes a message AS Pandius. AI is not invoked."""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Message text is required")
    text = request.text.strip()
    try:
        conv = await _load_conv_client(conversation_id, supabase)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        client = conv.get("pandius_clients") or {}

        await supabase.table("pandius_messages").insert({
            "conversation_id": str(conversation_id),
            "pandius_client_id": conv.get("pandius_client_id"),
            "direction": "outbound",
            "message_type": "text",
            "text": text,
            "sent_at": datetime.utcnow().isoformat(),
        }).execute()
        await supabase.table("pandius_conversations").update(
            {"last_activity_at": datetime.utcnow().isoformat()}
        ).eq("id", str(conversation_id)).execute()

        delivered = False
        chat_id = client.get("whatsapp_chat_id") or (
            f"{(client.get('phone') or '').replace('+', '')}@c.us" if client.get("phone") else None
        )
        if chat_id:
            try:
                from pandapower.integrations.green_api import get_green_api_client

                gclient = await get_green_api_client("pandius")
                if gclient:
                    result = await gclient.send_message(chat_id, text)
                    delivered = bool(result.get("success"))
                    await gclient.close()
            except Exception as send_err:
                logger.warning(f"Pandius WhatsApp send failed (message saved): {send_err}")

        return SendMessageResponse(text=text, delivered=delivered)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandius send_message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to send message")


@router.post("/conversations/{conversation_id}/pause", response_model=PauseResponse)
async def set_pandius_pause(
    conversation_id: UUID, request: PauseRequest,
    supabase=Depends(get_supabase_client),
):
    try:
        res = await supabase.table("pandius_conversations").update({
            "auto_reply_paused": request.paused,
            "last_activity_at": datetime.utcnow().isoformat(),
        }).eq("id", str(conversation_id)).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return PauseResponse(auto_reply_paused=request.paused)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandius set_pause failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update pause state")


@router.post("/conversations/{conversation_id}/close", response_model=CloseResponse)
async def set_pandius_close(
    conversation_id: UUID, request: CloseRequest,
    supabase=Depends(get_supabase_client),
):
    """Operator-initiated close (or reopen). Closing also pauses auto-reply."""
    try:
        if request.closed:
            update = {"status": "closed", "auto_reply_paused": True,
                      "last_activity_at": datetime.utcnow().isoformat()}
        else:
            update = {"status": "open", "auto_reply_paused": False,
                      "last_activity_at": datetime.utcnow().isoformat()}
        res = await supabase.table("pandius_conversations").update(update).eq(
            "id", str(conversation_id)
        ).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return CloseResponse(
            status=update["status"], auto_reply_paused=update["auto_reply_paused"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pandius set_close failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update conversation status")


@router.post("/conversations/{conversation_id}/generate", response_model=SendMessageResponse)
async def generate_pandius_reply(conversation_id: UUID, supabase=Depends(get_supabase_client)):
    """Run Pandius's engine on the latest inbound message and send the reply."""
    try:
        conv = await _load_conv_client(conversation_id, supabase)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        client = conv.get("pandius_clients") or {}

        last_inbound = await supabase.table("pandius_messages").select(
            "text"
        ).eq("conversation_id", str(conversation_id)).eq(
            "direction", "inbound"
        ).order("sent_at", desc=True).limit(1).execute()
        if not last_inbound.data or not (last_inbound.data[0].get("text") or "").strip():
            return SendMessageResponse(text="", delivered=False)

        chat_id = client.get("whatsapp_chat_id") or (
            f"{(client.get('phone') or '').replace('+', '')}@c.us" if client.get("phone") else ""
        )
        from pandapower.workers.pandius.conversation_handler import handle_candidate_message

        result = await handle_candidate_message(
            conversation_id=conversation_id,
            pandius_client_id=UUID(str(conv["pandius_client_id"])),
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
        logger.error(f"Pandius generate_reply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate reply")
