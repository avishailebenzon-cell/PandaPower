"""Admin routes for Pandi bot management."""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from pandapower.core.supabase import get_supabase_client
from pandapower.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/pandi", tags=["admin", "pandi"])


class GenerateInviteRequest(BaseModel):
    """Request to generate Pandi invite for a contact."""
    contact_id: UUID


class GenerateInviteResponse(BaseModel):
    """Response with generated invite details."""
    invite_url: str
    prefilled_message: str
    instructions_for_admin: str


class PandiClientListItem(BaseModel):
    """Pandi client in list view."""
    id: UUID
    phone: str
    contact_name: Optional[str]
    organization_name: Optional[str]
    identification_method: str
    intake_status: str
    first_message_at: Optional[datetime]
    last_message_at: Optional[datetime]
    is_active: bool


@router.post("/generate-invite", response_model=GenerateInviteResponse)
async def generate_pandi_invite(
    request: GenerateInviteRequest,
    supabase = Depends(get_supabase_client)
) -> GenerateInviteResponse:
    """Generate WhatsApp invite link for a contact.

    Args:
        request: Contact to invite
        supabase: Supabase client

    Returns:
        Invite URL and instructions
    """
    try:
        # Get contact details
        contact_result = supabase.table("contacts").select("*").eq(
            "id", str(request.contact_id)
        ).execute()

        if not contact_result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        contact = contact_result.data[0]
        contact_name = contact.get("name", "Unknown")

        # Check if pandi_client already exists for this contact
        client_result = supabase.table("pandi_clients").select("*").eq(
            "contact_id", str(request.contact_id)
        ).execute()

        if client_result.data:
            # Already invited
            client = client_result.data[0]
            client_id = client["id"]
            logger.info(f"Contact {request.contact_id} already has pandi_client {client_id}")
        else:
            # Create pandi_client record (no phone yet, will be populated on first message)
            client_data = {
                "contact_id": str(request.contact_id),
                "phone": "",  # Will be filled in from WhatsApp
                "intake_status": "not_started",
                "initial_invite_sent_at": datetime.utcnow().isoformat(),
                "initial_invite_sent_by_user_id": "system",  # TODO: Get from auth context
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            }

            client_result = supabase.table("pandi_clients").insert(client_data).execute()
            if not client_result.data:
                raise HTTPException(status_code=500, detail="Failed to create pandi client")

            client_id = client_result.data[0]["id"]
            logger.info(f"Created pandi_client {client_id} for contact {request.contact_id}")

        # Generate invite URL
        # Format: https://wa.me/{pandi_whatsapp_number}?text={prefilled_message_encoded}
        pandi_number = settings.pandi.whatsapp_number or "+972501234567"  # Placeholder
        if pandi_number.startswith("+"):
            pandi_number_clean = pandi_number[1:]
        else:
            pandi_number_clean = pandi_number

        # Prefilled message for client to send
        prefilled_msg = f"שלום פנדי! קבלתי את הקישור מ-{contact_name}. רוצה לחקור הזדמנויות חדשות 🐼"
        prefilled_msg_encoded = quote(prefilled_msg)

        invite_url = f"https://wa.me/{pandi_number_clean}?text={prefilled_msg_encoded}"

        # Instructions for admin to copy/paste
        admin_instructions = f"""היי {contact_name},

יש לנו בוט חדש שחושב שתאהב — הוא יודע למצוא לך מועמדים למשרות שלך. נסה אותו:

{invite_url}

(או שלח לי את ההודעה שלהלן בווטסאפ)"""

        return GenerateInviteResponse(
            invite_url=invite_url,
            prefilled_message=prefilled_msg,
            instructions_for_admin=admin_instructions
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate invite failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate invite")


@router.get("/clients", response_model=list[PandiClientListItem])
async def list_pandi_clients(
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    supabase = Depends(get_supabase_client)
) -> list[PandiClientListItem]:
    """List Pandi clients with optional filters.

    Args:
        is_active: Filter by active status
        limit: Pagination limit
        offset: Pagination offset
        supabase: Supabase client

    Returns:
        List of Pandi clients
    """
    try:
        # Query v_pandi_active_conversations view for rich data
        query = supabase.table("v_pandi_active_conversations").select("*")

        if is_active is not None:
            # Filter by is_active (would need custom view or join)
            pass

        result = query.range(offset, offset + limit - 1).execute()

        if not result.data:
            return []

        # Map to response model
        clients = []
        for row in result.data:
            clients.append(PandiClientListItem(
                id=row.get("pandi_client_id"),
                phone=row.get("phone", ""),
                contact_name=row.get("client_name"),
                organization_name=row.get("client_org_name"),
                identification_method="auto_phone_match",  # TODO: Get from pandi_clients table
                intake_status="completed",  # TODO: Get from pandi_clients table
                first_message_at=None,  # TODO: Get from pandi_clients table
                last_message_at=row.get("last_activity_at"),
                is_active=True  # TODO: Get from pandi_clients table
            ))

        return clients

    except Exception as e:
        logger.error(f"List pandi clients failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list clients")


@router.get("/clients/{client_id}")
async def get_pandi_client(
    client_id: str,
    supabase = Depends(get_supabase_client)
) -> dict:
    """Get detailed Pandi client profile.

    Args:
        client_id: Pandi client ID
        supabase: Supabase client

    Returns:
        Client details with conversation history
    """
    try:
        # Get client
        client_result = supabase.table("pandi_clients").select("*").eq(
            "id", client_id
        ).execute()

        if not client_result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        client = client_result.data[0]

        # Get contact and org
        contact_result = supabase.table("contacts").select("*").eq(
            "id", client["contact_id"]
        ).execute()
        contact = contact_result.data[0] if contact_result.data else {}

        org_result = supabase.table("organizations").select("*").eq(
            "id", contact.get("organization_id")
        ).execute()
        org = org_result.data[0] if org_result.data else {}

        # Get conversations (limit 10 recent)
        conv_result = supabase.table("pandi_conversations").select("*").eq(
            "pandi_client_id", client_id
        ).order("started_at", desc=True).limit(10).execute()
        conversations = conv_result.data or []

        return {
            "client": client,
            "contact": contact,
            "organization": org,
            "conversations": conversations
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get client failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get client")
