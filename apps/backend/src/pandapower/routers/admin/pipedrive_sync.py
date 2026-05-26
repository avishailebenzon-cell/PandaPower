"""Admin API endpoints for Pipedrive sync control."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/pipedrive-sync", tags=["admin", "pipedrive-sync"])


@router.post("/contacts")
async def trigger_contacts_sync():
    """Manually trigger full sync of Pipedrive contacts.

    Synchronizes all persons from Pipedrive and categorizes them in the contacts table:
    - employee (עובדים)
    - client (לקוחות)
    - potential_client (לקוחות פוטנציאלים)

    Returns:
        Sync summary with counts
    """
    try:
        logger.info("Manual contacts sync triggered")

        from pandapower.workers.pipedrive_sync import sync_pipedrive_contacts

        result = await sync_pipedrive_contacts()

        return {
            "status": "success",
            "message": "Contacts sync completed",
            "timestamp": datetime.utcnow().isoformat(),
            **result,
        }

    except Exception as e:
        logger.error(f"Manual contacts sync failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/contacts/status")
async def get_contacts_sync_status():
    """Get status of contacts sync.

    Returns:
        Latest sync information and current counts per category
    """
    try:
        db = await get_supabase_client()

        # Get last sync log
        sync_log = await db.table("pipedrive_sync_log").select("*").eq(
            "entity_type", "persons"
        ).order("started_at", desc=True).limit(1).execute()

        last_sync = sync_log.data[0] if sync_log.data else None

        # Get current counts from contacts table by contact_status
        employees_count = await db.table("contacts").select("id", count="exact").eq(
            "contact_status", "employee"
        ).execute()
        clients_count = await db.table("contacts").select("id", count="exact").eq(
            "contact_status", "client"
        ).execute()
        potential_count = await db.table("contacts").select("id", count="exact").eq(
            "contact_status", "potential_client"
        ).execute()
        total_count = await db.table("contacts").select("id", count="exact").execute()

        return {
            "status": "success",
            "last_sync": last_sync,
            "current_counts": {
                "employees": employees_count.count if hasattr(employees_count, "count") else 0,
                "clients": clients_count.count if hasattr(clients_count, "count") else 0,
                "potential_clients": potential_count.count if hasattr(potential_count, "count") else 0,
                "total": total_count.count if hasattr(total_count, "count") else 0,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get contacts sync status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")
