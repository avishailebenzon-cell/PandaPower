"""Company Profile settings — view the shared company-knowledge module and edit
the operator-added content that is injected into every agent (Tal, Elad, Pandi,
Dana).

The baseline (COMPANY_PROFILE + FACILITY_FACTS) is hardcoded and read-only; the
"extra" block is stored in system_settings and editable from the admin UI so
updates take effect without a redeploy.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pandapower.core.supabase import get_supabase_client
from pandapower.agents.company_profile import (
    COMPANY_PROFILE,
    FACILITY_FACTS,
    COMPANY_PROFILE_EXTRA_KEY,
    load_company_extra,
)

import structlog as _structlog

logger = _structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/company-profile", tags=["admin", "company-profile"])


class CompanyProfileResponse(BaseModel):
    """The full shared company module as shown in the settings screen."""
    base_company_profile: str
    base_facility_facts: str
    extra: str
    agents: list[str] = ["טל", "אלעד", "ליבי", "דנה"]


class UpdateExtraRequest(BaseModel):
    extra: str = Field(default="", max_length=8000)


@router.get("", response_model=CompanyProfileResponse)
async def get_company_profile(
    supabase=Depends(get_supabase_client),
) -> CompanyProfileResponse:
    """Return the read-only baseline plus the editable extra content."""
    try:
        extra = await load_company_extra(supabase)
    except Exception as e:
        logger.error("company_profile_get_failed", error=str(e))
        extra = ""
    return CompanyProfileResponse(
        base_company_profile=COMPANY_PROFILE,
        base_facility_facts=FACILITY_FACTS,
        extra=extra,
    )


@router.post("")
async def update_company_profile(
    request: UpdateExtraRequest,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Upsert the operator-added company content (stored as plain text)."""
    value = (request.extra or "").strip()
    now = datetime.utcnow().isoformat()
    try:
        existing = await supabase.table("system_settings").select("id").eq(
            "setting_key", COMPANY_PROFILE_EXTRA_KEY
        ).limit(1).execute()
        if existing.data:
            await supabase.table("system_settings").update(
                {"setting_value": value, "updated_at": now}
            ).eq("setting_key", COMPANY_PROFILE_EXTRA_KEY).execute()
        else:
            await supabase.table("system_settings").insert(
                {
                    "setting_key": COMPANY_PROFILE_EXTRA_KEY,
                    "setting_value": value,
                    "description": "Operator-added company knowledge shared by all agents",
                    "updated_at": now,
                }
            ).execute()
    except Exception as e:
        logger.error("company_profile_update_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

    logger.info("company_profile_updated", length=len(value))
    return {"status": "success", "extra": value}
