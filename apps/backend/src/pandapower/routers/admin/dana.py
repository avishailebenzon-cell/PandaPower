"""Admin routes for Dana — the AI sales agent that intakes new job deals.

Dana runs as a free-form web chat. The user describes a new role (and may
attach PDF/Word/image files); Dana extracts the details, de-dupes the contact
and organization, opens a deal in the right Pipedrive pipeline, and syncs it
into PandaPower for matching.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.agents.dana.conversation_engine import DanaConversationEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/dana", tags=["admin", "dana"])

OPENING_MESSAGE = (
    "היי אני דנה, אני אעזור לך להזין משרה חדשה למערכת ולפייפדרייב, "
    "תן לי את הנתונים הרלוונטיים"
)


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    text: str


class ConversationSummary(BaseModel):
    id: UUID
    title: Optional[str] = None
    status: str
    pipedrive_deal_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@router.post("/conversations")
async def create_conversation(supabase=Depends(get_supabase_client)) -> dict:
    """Start a new Dana conversation and seed her opening message."""
    try:
        res = await supabase.table("dana_conversations").insert({
            "status": "open",
            "job_context": {},
            "title": "משרה חדשה",
        }).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create conversation")
        conv = res.data[0]
        conversation_id = conv["id"]

        # Seed Dana's first message.
        await supabase.table("dana_messages").insert({
            "conversation_id": conversation_id,
            "direction": "outbound",
            "text": OPENING_MESSAGE,
            "llm_model": None,
        }).execute()

        return {
            "id": conversation_id,
            "status": "open",
            "opening_message": OPENING_MESSAGE,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dana create_conversation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create conversation")


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = 50, supabase=Depends(get_supabase_client)
) -> list[ConversationSummary]:
    try:
        res = (
            await supabase.table("dana_conversations")
            .select("id, title, status, pipedrive_deal_id, created_at, updated_at")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [ConversationSummary(**row) for row in (res.data or [])]
    except Exception as e:
        logger.error(f"Dana list_conversations failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: UUID, supabase=Depends(get_supabase_client)
) -> dict:
    try:
        conv = await supabase.table("dana_conversations").select("*").eq(
            "id", str(conversation_id)
        ).single().execute()
        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")

        msgs = (
            await supabase.table("dana_messages")
            .select("id, direction, text, sent_at")
            .eq("conversation_id", str(conversation_id))
            .order("sent_at", desc=False)
            .execute()
        )
        return {"conversation": conv.data, "messages": msgs.data or []}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dana get_conversation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@router.post("/conversations/{conversation_id}/message", response_model=MessageResponse)
async def send_message(
    conversation_id: UUID,
    request: MessageRequest,
    supabase=Depends(get_supabase_client),
) -> MessageResponse:
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Message text is required")
    try:
        engine = DanaConversationEngine()
        result = await engine.handle_message(conversation_id, request.text.strip())
        return MessageResponse(text=result["text"])
    except Exception as e:
        logger.error(f"Dana send_message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process message")


@router.post("/conversations/{conversation_id}/upload", response_model=MessageResponse)
async def upload_file(
    conversation_id: UUID,
    file: UploadFile = File(...),
    supabase=Depends(get_supabase_client),
) -> MessageResponse:
    """Accept a PDF/Word/image, extract its text, and feed it to Dana."""
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        extracted = await _extract_text(content, file.filename or "file")
        if not extracted or not extracted.strip():
            # Still record the attachment so Dana can ask for a clearer file.
            note = f"[קובץ מצורף: {file.filename}] — לא הצלחתי לחלץ טקסט מהקובץ."
        else:
            note = f"[קובץ מצורף: {file.filename}]\n{extracted.strip()}"

        engine = DanaConversationEngine()
        result = await engine.handle_message(conversation_id, note)
        return MessageResponse(text=result["text"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dana upload_file failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to process file")


async def _extract_text(content: bytes, filename: str) -> str:
    """Extract text from a document/image using ConvertAPI (OCR for images)."""
    from pandapower.integrations.convertapi_client import (
        ConvertApiClient,
        convertapi_src_token,
        get_convertapi_config,
    )

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    src = convertapi_src_token(ext, filename)
    if not src:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext or 'unknown'}",
        )

    cfg = await get_convertapi_config()
    secret = cfg.get("secret")
    if not secret:
        raise HTTPException(
            status_code=400,
            detail="ConvertAPI secret not configured — cannot parse files.",
        )

    client = ConvertApiClient(secret)
    try:
        return await client.to_text(
            content,
            src_format=src,
            ocr_languages=_safe_ocr_language(cfg.get("ocr_languages")),
        )
    finally:
        await client.close()


# ConvertAPI's /to/txt accepts a SINGLE OCR language token from a fixed list
# (Hebrew "he"/"heb" is NOT supported, and the multi-value "en,he" is rejected
# with a 400). 'auto' auto-detects the script (handles Hebrew CVs), so we
# sanitize whatever is configured down to a valid token, defaulting to 'auto'.
_CONVERTAPI_OCR_LANGS = {
    "auto", "ar", "ca", "zh", "da", "nl", "en", "fi", "fr", "de", "el", "ko",
    "it", "ja", "no", "pl", "pt", "ro", "ru", "sl", "es", "sv", "tr", "ua", "th",
}


def _safe_ocr_language(configured: Optional[str]) -> str:
    tokens = [t.strip().lower() for t in (configured or "").replace(",", " ").split() if t.strip()]
    # Honor a single explicitly-valid token; otherwise 'auto' (which detects
    # the script — best for mixed Hebrew/English documents anyway).
    if len(tokens) == 1 and tokens[0] in _CONVERTAPI_OCR_LANGS and tokens[0] != "auto":
        return tokens[0]
    return "auto"
