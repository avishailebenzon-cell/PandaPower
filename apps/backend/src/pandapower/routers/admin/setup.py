"""Admin setup endpoints for database migrations and initialization."""
import logging
from typing import Any

from fastapi import APIRouter

from pandapower.core.supabase import get_supabase_client
from pandapower.db.migrations import apply_migrations, init_system_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/setup", tags=["admin-setup"])


@router.post("/migrations")
async def run_migrations() -> dict[str, Any]:
    """Apply all pending database migrations."""
    try:
        supabase_client = await get_supabase_client()
        results = await apply_migrations(supabase_client)
        return results
    except Exception as e:
        logger.error(f"Migrations failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}


@router.post("/init-settings")
async def initialize_settings() -> dict[str, Any]:
    """Initialize default system settings."""
    try:
        supabase_client = await get_supabase_client()
        await init_system_settings(supabase_client)
        return {"status": "success", "settings_initialized": 6}
    except Exception as e:
        logger.error(f"Settings initialization failed: {e}", exc_info=True)
        return {"error": str(e), "status": "failed"}
