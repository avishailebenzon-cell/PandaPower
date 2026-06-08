"""Admin API for Pandi Outreach Campaigns (Session 35)

Invite premium clients to use Pandi for candidate sourcing.
Same implementation as Elad, different messaging.
"""

import logging
import string
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.green_api import get_green_api_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/pandi/outreach", tags=["admin", "pandi", "outreach"])


# Request/Response Models

class ContactPreview(BaseModel):
    """Contact for outreach selection"""
    id: str
    full_name: str
    email: str
    phone: str
    organization_name: Optional[str]
    domain: Optional[str]
    security_clearance_level: Optional[str]


class CampaignCreate(BaseModel):
    """Create new campaign"""
    campaign_name: str
    message_template: str
    filters: Optional[dict] = None  # {organization_ids, domains, clearance_levels}
    scheduled_start_at: Optional[datetime] = None


class Campaign(BaseModel):
    """Campaign details"""
    id: str
    campaign_name: str
    created_by_user_id: str
    message_template: str
    filters: Optional[dict]
    status: str
    total_contacts: int
    sent_count: int
    failed_count: int
    created_at: datetime


class PreviewMessageItem(BaseModel):
    """Message preview with contact"""
    contact: ContactPreview
    rendered_message: str


class CampaignPreviewResponse(BaseModel):
    """Campaign preview with contacts and messages"""
    campaign: Campaign
    preview_messages: list[PreviewMessageItem]


def _substitute_placeholders(template: str, contact: dict, company: str, phone: str) -> str:
    """Substitute placeholders in template: {client_name}, {company}, {phone}"""
    return template.format(
        client_name=contact.get("full_name", ""),
        company=company,
        phone=phone
    )


@router.get("/contacts", response_model=list[ContactPreview])
async def list_outreach_contacts(
    organization_ids: Optional[list[str]] = Query(None),
    domains: Optional[list[str]] = Query(None),
    clearance_levels: Optional[list[str]] = Query(None),
    limit: int = 100,
    offset: int = 0,
    supabase=Depends(get_supabase_client)
) -> list[ContactPreview]:
    """List contacts for outreach with optional filters"""
    try:
        # Build query: start with all clients
        query = supabase.table("contacts").select(
            """
            id,
            full_name,
            email,
            phone,
            domain,
            security_clearance_level,
            organization_id,
            organizations(name)
            """
        ).eq("contact_status", "client")

        # Apply filters
        if organization_ids:
            query = query.in_("organization_id", organization_ids)
        if domains:
            query = query.in_("domain", domains)
        if clearance_levels:
            query = query.in_("security_clearance_level", clearance_levels)

        # Execute
        result = await query.order("full_name", desc=False).range(offset, offset + limit - 1).execute()

        contacts = []
        for row in result.data or []:
            org_data = row.get("organizations") or {}
            contacts.append(ContactPreview(
                id=row.get("id"),
                full_name=row.get("full_name", ""),
                email=row.get("email", ""),
                phone=row.get("phone", ""),
                organization_name=org_data.get("name") if isinstance(org_data, dict) else None,
                domain=row.get("domain"),
                security_clearance_level=row.get("security_clearance_level")
            ))

        logger.info(f"Listed {len(contacts)} outreach contacts")
        return contacts

    except Exception as e:
        logger.error(f"Failed to list outreach contacts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns", response_model=Campaign)
async def create_campaign(
    request: CampaignCreate,
    supabase=Depends(get_supabase_client)
) -> Campaign:
    """Create new outreach campaign"""
    try:
        # Get authenticated user
        admin_result = await supabase.table("user_roles").select("user_id").eq(
            "role_name", "admin"
        ).limit(1).execute()

        user_id = admin_result.data[0]["user_id"] if admin_result.data else None
        if not user_id:
            raise HTTPException(status_code=403, detail="No admin user found")

        # Create campaign
        result = await supabase.table("pandi_outreach_campaigns").insert({
            "campaign_name": request.campaign_name,
            "created_by_user_id": user_id,
            "message_template": request.message_template,
            "filters": request.filters or {},
            "status": "draft",
            "scheduled_start_at": request.scheduled_start_at,
        }).execute()

        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to create campaign")

        campaign = result.data[0]
        logger.info(f"Created campaign: {campaign.get('id')}")

        return Campaign(
            id=campaign.get("id"),
            campaign_name=campaign.get("campaign_name"),
            created_by_user_id=campaign.get("created_by_user_id"),
            message_template=campaign.get("message_template"),
            filters=campaign.get("filters"),
            status=campaign.get("status"),
            total_contacts=campaign.get("total_contacts", 0),
            sent_count=campaign.get("sent_count", 0),
            failed_count=campaign.get("failed_count", 0),
            created_at=datetime.fromisoformat(campaign.get("created_at"))
        )

    except Exception as e:
        logger.error(f"Failed to create campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/{campaign_id}/preview", response_model=CampaignPreviewResponse)
async def preview_campaign(
    campaign_id: str,
    limit: int = 10,
    offset: int = 0,
    supabase=Depends(get_supabase_client)
) -> CampaignPreviewResponse:
    """Preview campaign: show selected contacts and rendered messages"""
    try:
        # Get campaign
        campaign_result = await supabase.table("pandi_outreach_campaigns").select("*").eq(
            "id", campaign_id
        ).single()

        if not campaign_result:
            raise HTTPException(status_code=404, detail="Campaign not found")

        campaign = campaign_result

        # Get Pandi's Green API config (for phone number)
        try:
            pandi_client = await get_green_api_client("pandi")
            pandi_phone = pandi_client.phone if hasattr(pandi_client, 'phone') else "+972XXXXXXX"
        except Exception:
            pandi_phone = "+972XXXXXXX"

        # Get contacts based on filters
        filters = campaign.get("filters") or {}
        query = supabase.table("contacts").select(
            """
            id,
            full_name,
            email,
            phone,
            domain,
            security_clearance_level,
            organization_id,
            organizations(name)
            """
        ).eq("contact_status", "client")

        if filters.get("organization_ids"):
            query = query.in_("organization_id", filters["organization_ids"])
        if filters.get("domains"):
            query = query.in_("domain", filters["domains"])
        if filters.get("clearance_levels"):
            query = query.in_("security_clearance_level", filters["clearance_levels"])

        result = await query.order("full_name", desc=False).range(offset, offset + limit - 1).execute()

        preview_messages = []
        for row in result.data or []:
            org_data = row.get("organizations") or {}
            contact = ContactPreview(
                id=row.get("id"),
                full_name=row.get("full_name", ""),
                email=row.get("email", ""),
                phone=row.get("phone", ""),
                organization_name=org_data.get("name") if isinstance(org_data, dict) else None,
                domain=row.get("domain"),
                security_clearance_level=row.get("security_clearance_level")
            )

            # Render message
            company_name = contact.organization_name or "PandaTech"
            rendered = _substitute_placeholders(
                campaign.get("message_template"),
                {"full_name": contact.full_name},
                company_name,
                pandi_phone
            )

            preview_messages.append(PreviewMessageItem(
                contact=contact,
                rendered_message=rendered
            ))

        return CampaignPreviewResponse(
            campaign=Campaign(
                id=campaign.get("id"),
                campaign_name=campaign.get("campaign_name"),
                created_by_user_id=campaign.get("created_by_user_id"),
                message_template=campaign.get("message_template"),
                filters=campaign.get("filters"),
                status=campaign.get("status"),
                total_contacts=campaign.get("total_contacts", 0),
                sent_count=campaign.get("sent_count", 0),
                failed_count=campaign.get("failed_count", 0),
                created_at=datetime.fromisoformat(campaign.get("created_at"))
            ),
            preview_messages=preview_messages
        )

    except Exception as e:
        logger.error(f"Failed to preview campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    request: dict,
    supabase=Depends(get_supabase_client)
) -> dict:
    """Send campaign: queue all pending messages.

    DISABLED: Pandi is an inbound-only agent — she responds to clients who
    reach out and never initiates outreach. Outbound campaigns belong to Elad.
    This endpoint is intentionally blocked.
    """
    raise HTTPException(
        status_code=403,
        detail=(
            "פנדי היא סוכנת נכנסת (inbound) בלבד ואינה יוזמת פנייה ללקוחות. "
            "קמפיינים יוצאים מתבצעים דרך אלעד (Elad)."
        ),
    )

    try:  # pragma: no cover - unreachable, kept for easy re-enable
        confirm = request.get("confirm", False)
        if not confirm:
            raise HTTPException(status_code=400, detail="confirm must be true")

        # Get campaign
        campaign = await supabase.table("pandi_outreach_campaigns").select("*").eq(
            "id", campaign_id
        ).single()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Get Pandi Green API config
        pandi_client = await get_green_api_client("pandi")
        if not pandi_client:
            raise HTTPException(status_code=500, detail="Pandi WhatsApp not configured")

        # Get contacts based on filters
        filters = campaign.get("filters") or {}
        query = supabase.table("contacts").select(
            "id, full_name, phone, organization_id, organizations(name)"
        ).eq("contact_status", "client")

        if filters.get("organization_ids"):
            query = query.in_("organization_id", filters["organization_ids"])
        if filters.get("domains"):
            query = query.in_("domain", filters["domains"])
        if filters.get("clearance_levels"):
            query = query.in_("security_clearance_level", filters["clearance_levels"])

        result = await query.execute()
        contacts = result.data or []

        # Create outreach messages
        messages_to_create = []
        for contact in contacts:
            org_data = contact.get("organizations") or {}
            company_name = org_data.get("name") if isinstance(org_data, dict) else "PandaTech"
            phone = contact.get("phone", "")

            # Normalize phone to WhatsApp format
            if phone:
                chat_id = phone.replace("+", "").replace("-", "").replace(" ", "")
                if not chat_id.startswith("972"):
                    if chat_id.startswith("0"):
                        chat_id = "972" + chat_id[1:]
                    else:
                        chat_id = "972" + chat_id
                chat_id = f"{chat_id}@c.us"
            else:
                chat_id = None

            # Render message
            rendered_msg = _substitute_placeholders(
                campaign.get("message_template"),
                contact,
                company_name,
                pandi_client.phone if hasattr(pandi_client, 'phone') else "+972XXXXXXX"
            )

            messages_to_create.append({
                "campaign_id": campaign_id,
                "contact_id": contact.get("id"),
                "message_text": rendered_msg,
                "green_api_chat_id": chat_id,
                "status": "pending"
            })

        # Batch insert messages
        if messages_to_create:
            await supabase.table("pandi_outreach_messages").insert(messages_to_create).execute()

        # Update campaign: set status=in_progress, total_contacts
        await supabase.table("pandi_outreach_campaigns").update({
            "status": "in_progress",
            "total_contacts": len(contacts),
            "started_at": datetime.utcnow().isoformat()
        }).eq("id", campaign_id).execute()

        # Queue Celery task
        try:
            from pandapower.workers.pandi.outreach_sender import process_pandi_outreach
            task = process_pandi_outreach.delay(campaign_id)
            logger.info(f"Queued outreach task {task.id} for campaign {campaign_id}")
        except Exception as e:
            logger.warning(f"Failed to queue Celery task: {e}")

        return {
            "status": "in_progress",
            "campaign_id": campaign_id,
            "total_contacts": len(contacts),
            "estimated_duration_seconds": len(contacts) * 3
        }

    except Exception as e:
        logger.error(f"Failed to send campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns/{campaign_id}", response_model=Campaign)
async def get_campaign(
    campaign_id: str,
    supabase=Depends(get_supabase_client)
) -> Campaign:
    """Get campaign details with stats"""
    try:
        result = await supabase.table("pandi_outreach_campaigns").select("*").eq(
            "id", campaign_id
        ).single()

        if not result:
            raise HTTPException(status_code=404, detail="Campaign not found")

        campaign = result
        return Campaign(
            id=campaign.get("id"),
            campaign_name=campaign.get("campaign_name"),
            created_by_user_id=campaign.get("created_by_user_id"),
            message_template=campaign.get("message_template"),
            filters=campaign.get("filters"),
            status=campaign.get("status"),
            total_contacts=campaign.get("total_contacts", 0),
            sent_count=campaign.get("sent_count", 0),
            failed_count=campaign.get("failed_count", 0),
            created_at=datetime.fromisoformat(campaign.get("created_at"))
        )

    except Exception as e:
        logger.error(f"Failed to get campaign: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaigns", response_model=list[Campaign])
async def list_campaigns(
    limit: int = 20,
    offset: int = 0,
    supabase=Depends(get_supabase_client)
) -> list[Campaign]:
    """List all campaigns (recent first)"""
    try:
        result = await supabase.table("pandi_outreach_campaigns").select("*").order(
            "created_at", desc=True
        ).range(offset, offset + limit - 1).execute()

        campaigns = []
        for row in result.data or []:
            campaigns.append(Campaign(
                id=row.get("id"),
                campaign_name=row.get("campaign_name"),
                created_by_user_id=row.get("created_by_user_id"),
                message_template=row.get("message_template"),
                filters=row.get("filters"),
                status=row.get("status"),
                total_contacts=row.get("total_contacts", 0),
                sent_count=row.get("sent_count", 0),
                failed_count=row.get("failed_count", 0),
                created_at=datetime.fromisoformat(row.get("created_at"))
            ))

        return campaigns

    except Exception as e:
        logger.error(f"Failed to list campaigns: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
