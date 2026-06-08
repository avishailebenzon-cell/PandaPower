"""Admin routes for Pandius bot management (candidate-facing agent)."""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/pandius", tags=["admin", "pandius"])


class PandiusClientListItem(BaseModel):
    id: UUID
    phone: str
    candidate_name: Optional[str] = None
    intake_status: str = "not_started"
    cv_received: bool = False
    first_message_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    is_active: bool = True


def _name(client: dict) -> Optional[str]:
    collected = client.get("intake_collected_data") or {}
    if isinstance(collected, dict) and collected.get("name"):
        return str(collected["name"])
    return None


@router.get("/clients", response_model=list[PandiusClientListItem])
async def list_pandius_clients(
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    supabase=Depends(get_supabase_client),
) -> list[PandiusClientListItem]:
    try:
        query = supabase.table("pandius_clients").select("*").order(
            "last_message_at", desc=True
        )
        if is_active is not None:
            query = query.eq("is_active", is_active)
        result = await query.range(offset, offset + limit - 1).execute()

        return [
            PandiusClientListItem(
                id=row["id"],
                phone=row.get("phone", ""),
                candidate_name=_name(row),
                intake_status=row.get("intake_status") or "not_started",
                cv_received=bool(row.get("cv_received_at")),
                first_message_at=row.get("first_message_at"),
                last_message_at=row.get("last_message_at"),
                is_active=bool(row.get("is_active", True)),
            )
            for row in (result.data or [])
        ]
    except Exception as e:
        logger.error(f"List pandius clients failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list clients")


@router.get("/clients/{client_id}")
async def get_pandius_client(
    client_id: str, supabase=Depends(get_supabase_client)
) -> dict:
    try:
        client_result = await supabase.table("pandius_clients").select("*").eq(
            "id", client_id
        ).limit(1).execute()
        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")
        client = client_result.data[0]

        contact = {}
        if client.get("contact_id"):
            contact_result = await supabase.table("contacts").select("*").eq(
                "id", client["contact_id"]
            ).limit(1).execute()
            contact = contact_result.data[0] if contact_result.data else {}

        conv_result = await supabase.table("pandius_conversations").select("*").eq(
            "pandius_client_id", client_id
        ).order("started_at", desc=True).limit(10).execute()

        return {
            "client": client,
            "contact": contact,
            "conversations": conv_result.data or [],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get pandius client failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get client")
