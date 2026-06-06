"""System Settings Management (Phase 34)"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from pandapower.core.supabase import get_supabase_client

import structlog as _structlog
logger = _structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/system", tags=["admin", "system"])


class SystemSettings(BaseModel):
    """System configuration settings"""
    pandi_manager_email: str
    pandi_sla_hours: int = 48
    pandi_enabled: bool = True
    notification_channel: str = "email"  # email, slack, telegram


class UpdateSettingsRequest(BaseModel):
    """Update system settings"""
    pandi_manager_email: Optional[EmailStr] = None
    pandi_sla_hours: Optional[int] = None
    pandi_enabled: Optional[bool] = None
    notification_channel: Optional[str] = None


@router.get("/settings", response_model=SystemSettings)
async def get_settings(
    supabase=Depends(get_supabase_client)
) -> SystemSettings:
    """Get current system settings."""
    try:
        result = await supabase.table("system_settings").select(
            "setting_key, setting_value"
        ).execute()

        settings = {
            "pandi_manager_email": "avishai.lebenzon@gmail.com",
            "pandi_sla_hours": 48,
            "pandi_enabled": True,
            "notification_channel": "email",
        }

        for row in result.data or []:
            key = row.get("setting_key", "").replace("pandi.", "")
            value = row.get("setting_value", {}).get("value")

            if key in settings and value is not None:
                settings[key] = value

        return SystemSettings(**settings)

    except Exception as e:
        logger.error(f"Failed to get settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def update_settings(
    request: UpdateSettingsRequest,
    supabase=Depends(get_supabase_client)
) -> dict:
    """Update system settings."""
    try:
        updates = []

        if request.pandi_manager_email:
            updates.append({
                "setting_key": "pandi.manager_email",
                "setting_value": {"value": request.pandi_manager_email},
                "description": "Email address of the Pandi referral manager",
            })

        if request.pandi_sla_hours is not None:
            updates.append({
                "setting_key": "pandi.sla_hours",
                "setting_value": {"value": request.pandi_sla_hours},
                "description": "SLA hours for Pandi referrals (default 48)",
            })

        if request.pandi_enabled is not None:
            updates.append({
                "setting_key": "pandi.enabled",
                "setting_value": {"value": request.pandi_enabled},
                "description": "Enable/disable Pandi bot",
            })

        if request.notification_channel:
            updates.append({
                "setting_key": "pandi.notification_channel",
                "setting_value": {"value": request.notification_channel},
                "description": "Notification channel (email, slack, telegram)",
            })

        for update in updates:
            # Try upsert (update if exists, insert if not)
            existing = await supabase.table("system_settings").select(
                "id"
            ).eq("setting_key", update["setting_key"]).single()

            if existing:
                await supabase.table("system_settings").update({
                    "setting_value": update["setting_value"],
                }).eq("setting_key", update["setting_key"])
            else:
                await supabase.table("system_settings").insert(update)

        logger.info("system_settings_updated", updates=len(updates))

        return {
            "status": "success",
            "message": f"Updated {len(updates)} settings",
        }

    except Exception as e:
        logger.error(f"Failed to update settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
