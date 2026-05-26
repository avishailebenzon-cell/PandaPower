"""Quota management for Pandi message limits."""

import logging
from datetime import datetime, date
from typing import Any

logger = logging.getLogger(__name__)


async def initialize_quota(client_id: str, supabase: Any, month: date = None) -> dict[str, Any]:
    """Initialize monthly quota for a Pandi client.

    Args:
        client_id: Pandi client ID
        supabase: Supabase client
        month: Calendar month (defaults to today's month)

    Returns:
        Quota creation result
    """
    try:
        if month is None:
            today = date.today()
            month = today.replace(day=1)

        # Get default limit from settings
        settings_result = supabase.table("system_settings").select("value").eq(
            "key", "pandi.default_monthly_limit"
        ).execute()

        monthly_limit = 100  # Default fallback
        if settings_result.data:
            try:
                monthly_limit = int(settings_result.data[0]["value"])
            except (ValueError, TypeError):
                pass

        # Check if quota already exists for this month
        existing = supabase.table("pandi_message_quotas").select("id").eq(
            "pandi_client_id", client_id
        ).eq("month", month.isoformat()).execute()

        if existing.data:
            logger.info(f"Quota already exists for client {client_id}, month {month}")
            return {
                "status": "skipped",
                "reason": "Quota already exists"
            }

        # Create quota record
        quota_data = {
            "pandi_client_id": client_id,
            "month": month.isoformat(),
            "monthly_limit": monthly_limit,
            "messages_used": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        quota_result = supabase.table("pandi_message_quotas").insert(quota_data).execute()

        if not quota_result.data:
            logger.error(f"Failed to create quota for client {client_id}")
            return {"status": "failed", "reason": "Quota creation failed"}

        quota_id = quota_result.data[0]["id"]
        logger.info(f"Created quota {quota_id} for client {client_id}, limit={monthly_limit}")

        return {
            "status": "created",
            "quota_id": quota_id,
            "monthly_limit": monthly_limit,
            "month": month.isoformat()
        }

    except Exception as e:
        logger.error(f"Quota initialization failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def check_quota(client_id: str, supabase: Any) -> dict[str, Any]:
    """Check if client has available quota for messages.

    Args:
        client_id: Pandi client ID
        supabase: Supabase client

    Returns:
        {has_quota: bool, messages_used: int, limit: int, remaining: int}
    """
    try:
        today = date.today()
        month = today.replace(day=1)

        # Get quota for this month
        quota_result = supabase.table("pandi_message_quotas").select("*").eq(
            "pandi_client_id", client_id
        ).eq("month", month.isoformat()).execute()

        if not quota_result.data:
            logger.warning(f"No quota found for client {client_id}, month {month}")
            return {
                "has_quota": False,
                "reason": "No quota for this month"
            }

        quota = quota_result.data[0]
        messages_used = quota.get("messages_used", 0)
        monthly_limit = quota.get("monthly_limit", 100)
        increase_approved = quota.get("increase_approved_amount", 0)
        total_available = monthly_limit + increase_approved
        remaining = total_available - messages_used

        has_quota = remaining > 0

        logger.info(f"Quota check for {client_id}: {messages_used}/{total_available}")

        return {
            "has_quota": has_quota,
            "messages_used": messages_used,
            "monthly_limit": monthly_limit,
            "increase_approved_amount": increase_approved,
            "total_available": total_available,
            "remaining": remaining,
            "quota_id": quota.get("id")
        }

    except Exception as e:
        logger.error(f"Quota check failed: {e}", exc_info=True)
        return {
            "has_quota": False,
            "error": str(e)
        }


async def increment_quota_usage(client_id: str, message_count: int, supabase: Any) -> dict[str, Any]:
    """Increment message usage counter for client's quota.

    Args:
        client_id: Pandi client ID
        message_count: Number of messages to add (typically 1)
        supabase: Supabase client

    Returns:
        Updated quota info
    """
    try:
        today = date.today()
        month = today.replace(day=1)

        # Get current quota
        quota_result = supabase.table("pandi_message_quotas").select("*").eq(
            "pandi_client_id", client_id
        ).eq("month", month.isoformat()).execute()

        if not quota_result.data:
            logger.warning(f"No quota found for client {client_id}")
            return {"status": "failed", "reason": "No quota for this month"}

        quota = quota_result.data[0]
        new_usage = quota.get("messages_used", 0) + message_count

        # Update quota
        supabase.table("pandi_message_quotas").update({
            "messages_used": new_usage,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", quota.get("id")).execute()

        logger.info(f"Updated quota for {client_id}: {new_usage} messages used")

        return {
            "status": "updated",
            "messages_used": new_usage,
            "quota_id": quota.get("id")
        }

    except Exception as e:
        logger.error(f"Quota increment failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
