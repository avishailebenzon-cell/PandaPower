"""Admin API for Pandi Referral Management (Phase 34)"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/pandi", tags=["admin", "pandi"])


class ReferralListItem(BaseModel):
    """Referral in list view"""
    referral_number: str
    candidate_number: str
    client_name: Optional[str]
    status: str
    sla_deadline: Optional[datetime]
    is_sla_breached: bool
    presented_at: datetime
    created_at: datetime


class ReferralDetail(BaseModel):
    """Full referral detail"""
    referral_number: str
    referral_id: str
    candidate_number: str
    client_name: Optional[str]
    client_phone: Optional[str]
    status: str
    sla_deadline: Optional[datetime]
    is_sla_breached: bool
    job_context: Optional[dict]
    presented_payload: dict
    llm_match_reasoning: Optional[str]
    status_notes: Optional[str]
    presented_at: datetime
    created_at: datetime


@router.get("/referrals", response_model=list[ReferralListItem])
async def list_referrals(
    status: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    supabase=Depends(get_supabase_client)
) -> list[ReferralListItem]:
    """List all active referrals with SLA tracking.

    Args:
        status: Filter by status (client_interested, in_recruitment_process, etc)
        sla_breached: Filter by SLA breach status
    """
    try:
        query = supabase.table("candidate_referrals").select(
            """
            referral_number,
            candidate_number,
            status,
            sla_deadline,
            presented_at,
            created_at,
            pandi_clients(
              contact_id->contacts(full_name, phone)
            )
            """
        )

        # Filter by status
        if status:
            query = query.eq("status", status)
        else:
            # Default: exclude terminal states (hired, rejected_by_us)
            query = query.not_.in_("status", ["hired", "rejected_by_us"])

        # Order by SLA deadline (breached first)
        result = await query.order("sla_deadline", desc=False).execute()

        referrals = []
        now = datetime.utcnow()

        for row in result.data or []:
            sla_deadline = row.get("sla_deadline")
            is_breached = sla_deadline and datetime.fromisoformat(sla_deadline) < now

            # Filter by SLA breach if specified
            if sla_breached is not None and is_breached != sla_breached:
                continue

            client_contact = row.get("pandi_clients", {}).get("contact_id", {})

            referrals.append(ReferralListItem(
                referral_number=row.get("referral_number", "N/A"),
                candidate_number=row.get("candidate_number"),
                client_name=client_contact.get("full_name"),
                status=row.get("status"),
                sla_deadline=datetime.fromisoformat(sla_deadline) if sla_deadline else None,
                is_sla_breached=is_breached,
                presented_at=datetime.fromisoformat(row.get("presented_at")),
                created_at=datetime.fromisoformat(row.get("created_at")),
            ))

        logger.info(f"Listed {len(referrals)} referrals")
        return referrals

    except Exception as e:
        logger.error(f"Failed to list referrals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/referrals/{referral_number}", response_model=ReferralDetail)
async def get_referral(
    referral_number: str,
    supabase=Depends(get_supabase_client)
) -> ReferralDetail:
    """Get full details of a specific referral."""
    try:
        result = await supabase.table("candidate_referrals").select(
            """
            id,
            referral_number,
            candidate_number,
            status,
            sla_deadline,
            job_context,
            presented_payload,
            llm_match_reasoning,
            status_notes,
            presented_at,
            created_at,
            pandi_clients(
              contact_id->contacts(full_name, phone)
            )
            """
        ).eq("referral_number", referral_number).single()

        if not result:
            raise HTTPException(status_code=404, detail="Referral not found")

        sla_deadline = result.get("sla_deadline")
        is_breached = sla_deadline and datetime.fromisoformat(sla_deadline) < datetime.utcnow()

        client_contact = result.get("pandi_clients", {}).get("contact_id", {})

        return ReferralDetail(
            referral_id=result.get("id"),
            referral_number=result.get("referral_number"),
            candidate_number=result.get("candidate_number"),
            client_name=client_contact.get("full_name"),
            client_phone=client_contact.get("phone"),
            status=result.get("status"),
            sla_deadline=datetime.fromisoformat(sla_deadline) if sla_deadline else None,
            is_sla_breached=is_breached,
            job_context=result.get("job_context"),
            presented_payload=result.get("presented_payload", {}),
            llm_match_reasoning=result.get("llm_match_reasoning"),
            status_notes=result.get("status_notes"),
            presented_at=datetime.fromisoformat(result.get("presented_at")),
            created_at=datetime.fromisoformat(result.get("created_at")),
        )

    except Exception as e:
        logger.error(f"Failed to get referral {referral_number}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/referrals/{referral_number}/status")
async def update_referral_status(
    referral_number: str,
    new_status: str,
    notes: Optional[str] = None,
    supabase=Depends(get_supabase_client)
) -> dict:
    """Update referral status (e.g., client_interested → in_recruitment_process)."""
    try:
        # Get current referral
        referral = await supabase.table("candidate_referrals").select(
            "id, status"
        ).eq("referral_number", referral_number).single()

        if not referral:
            raise HTTPException(status_code=404, detail="Referral not found")

        current_status = referral.get("status")

        # Validate transition
        valid_transitions = {
            "presented": ["client_interested", "client_declined"],
            "client_interested": ["in_recruitment_process", "client_declined"],
            "in_recruitment_process": ["hired", "rejected_by_client"],
        }

        if current_status not in valid_transitions or new_status not in valid_transitions.get(current_status, []):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from {current_status} to {new_status}"
            )

        # Update referral
        await supabase.table("candidate_referrals").update({
            "status": new_status,
            "status_updated_at": datetime.utcnow().isoformat(),
            "status_notes": notes,
        }).eq("id", referral["id"])

        logger.info(
            "referral_status_updated",
            referral_number=referral_number,
            from_status=current_status,
            to_status=new_status,
        )

        return {
            "status": "success",
            "referral_number": referral_number,
            "new_status": new_status,
        }

    except Exception as e:
        logger.error(f"Failed to update referral status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
