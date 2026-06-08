"""WhatsApp-style conversation screens for the recruiter chat agents.

One factory builds an identical API for each recruiter that runs over the
recruiter_conversations / recruiter_messages tables:
  • Tal  (/admin/tal)  — initial screening, conversations with candidates.
  • Elad (/admin/elad) — placements, conversations with clients.

Each exposes:
  GET  /conversations                       — list (newest activity first)
  GET  /conversations/{id}                  — detail + messages
  POST /conversations/{id}/send  {text}     — operator writes AS the agent
  POST /conversations/{id}/pause {paused}   — toggle AI auto-reply (takeover)
  POST /conversations/{id}/generate         — manually trigger the agent's reply
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.agents.recruiter_chat.engine import RecruiterChatEngine

logger = logging.getLogger(__name__)


# ---- Shared response models ------------------------------------------------

class ConversationSummary(BaseModel):
    id: str
    match_id: Optional[str] = None
    candidate_name: str = "מועמד"
    job_title: str = ""
    status: str = "active"
    auto_reply_paused: bool = False
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None
    started_at: Optional[str] = None


class ChatMessage(BaseModel):
    id: str
    direction: str  # inbound | outbound
    text: Optional[str] = None
    author: Optional[str] = None  # agent | human | candidate
    created_at: Optional[str] = None


class ConversationDetail(BaseModel):
    id: str
    match_id: Optional[str] = None
    candidate_name: str = "מועמד"
    job_title: str = ""
    status: str = "active"
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


def make_recruiter_chat_router(recruiter: str) -> APIRouter:
    """Build the conversations API for one recruiter ('tal' or 'elad')."""
    router = APIRouter(prefix=f"/admin/{recruiter}", tags=["admin", recruiter, "chat"])

    @router.get("/conversations", response_model=List[ConversationSummary])
    async def list_conversations(limit: int = 100, supabase=Depends(get_supabase_client)):
        try:
            res = await supabase.table("recruiter_conversations").select(
                "id, match_id, status, auto_reply_paused, started_at, updated_at, "
                "matches(candidates(name), jobs(job_title))"
            ).eq("recruiter", recruiter).order("updated_at", desc=True).limit(limit).execute()

            out: List[ConversationSummary] = []
            for conv in res.data or []:
                match = conv.get("matches") or {}
                cand = (match.get("candidates") or {}) if isinstance(match, dict) else {}
                job = (match.get("jobs") or {}) if isinstance(match, dict) else {}

                last_text, last_at = None, None
                try:
                    msg_res = await supabase.table("recruiter_messages").select(
                        "text, created_at"
                    ).eq("conversation_id", conv["id"]).order(
                        "created_at", desc=True
                    ).limit(1).execute()
                    if msg_res.data:
                        last_text = msg_res.data[0].get("text")
                        last_at = msg_res.data[0].get("created_at")
                except Exception:
                    pass

                out.append(ConversationSummary(
                    id=conv["id"],
                    match_id=conv.get("match_id"),
                    candidate_name=cand.get("name") or "מועמד" if isinstance(cand, dict) else "מועמד",
                    job_title=job.get("job_title") or "" if isinstance(job, dict) else "",
                    status=conv.get("status") or "active",
                    auto_reply_paused=bool(conv.get("auto_reply_paused")),
                    last_message=last_text,
                    last_message_at=last_at,
                    started_at=conv.get("started_at"),
                ))
            return out
        except Exception as e:
            logger.error(f"{recruiter} list_conversations failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to list conversations")

    @router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
    async def get_conversation(conversation_id: UUID, supabase=Depends(get_supabase_client)):
        try:
            res = await supabase.table("recruiter_conversations").select(
                "id, match_id, status, auto_reply_paused, "
                "matches(candidates(name), jobs(job_title))"
            ).eq("id", str(conversation_id)).eq("recruiter", recruiter).limit(1).execute()
            if not res.data:
                raise HTTPException(status_code=404, detail="Conversation not found")
            conv = res.data[0]
            match = conv.get("matches") or {}
            cand = (match.get("candidates") or {}) if isinstance(match, dict) else {}
            job = (match.get("jobs") or {}) if isinstance(match, dict) else {}

            msg_res = await supabase.table("recruiter_messages").select(
                "id, direction, text, author, created_at"
            ).eq("conversation_id", str(conversation_id)).order(
                "created_at", desc=False
            ).execute()
            messages = [
                ChatMessage(
                    id=m["id"],
                    direction=m.get("direction", "outbound"),
                    text=m.get("text"),
                    author=m.get("author"),
                    created_at=m.get("created_at"),
                )
                for m in (msg_res.data or [])
            ]
            return ConversationDetail(
                id=conv["id"],
                match_id=conv.get("match_id"),
                candidate_name=cand.get("name") or "מועמד" if isinstance(cand, dict) else "מועמד",
                job_title=job.get("job_title") or "" if isinstance(job, dict) else "",
                status=conv.get("status") or "active",
                auto_reply_paused=bool(conv.get("auto_reply_paused")),
                messages=messages,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"{recruiter} get_conversation failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to get conversation")

    @router.post("/conversations/{conversation_id}/send", response_model=SendMessageResponse)
    async def send_message(
        conversation_id: UUID, request: SendMessageRequest,
        supabase=Depends(get_supabase_client),
    ):
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Message text is required")
        try:
            engine = RecruiterChatEngine(recruiter)
            result = await engine.save_human_message(conversation_id, request.text.strip())
            return SendMessageResponse(text=result["text"], delivered=bool(result.get("delivered")))
        except Exception as e:
            logger.error(f"{recruiter} send_message failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to send message")

    @router.post("/conversations/{conversation_id}/pause", response_model=PauseResponse)
    async def set_pause(
        conversation_id: UUID, request: PauseRequest,
        supabase=Depends(get_supabase_client),
    ):
        try:
            res = await supabase.table("recruiter_conversations").update({
                "auto_reply_paused": request.paused,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("id", str(conversation_id)).eq("recruiter", recruiter).execute()
            if not res.data:
                raise HTTPException(status_code=404, detail="Conversation not found")
            return PauseResponse(auto_reply_paused=request.paused)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"{recruiter} set_pause failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to update pause state")

    @router.post("/conversations/{conversation_id}/generate", response_model=SendMessageResponse)
    async def generate_reply(conversation_id: UUID, supabase=Depends(get_supabase_client)):
        try:
            engine = RecruiterChatEngine(recruiter)
            result = await engine.generate_reply(conversation_id)
            return SendMessageResponse(
                text=result.get("text", ""),
                delivered=not result.get("skipped", False),
            )
        except Exception as e:
            logger.error(f"{recruiter} generate_reply failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to generate reply")

    return router


tal_router = make_recruiter_chat_router("tal")
elad_router = make_recruiter_chat_router("elad")
