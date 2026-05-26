import logging
from typing import Any

from supabase import AsyncClient, create_client

from pandapower.core.config import settings

logger = logging.getLogger(__name__)

_supabase_client: Any | None = None


async def init_supabase():
    """Initialize Supabase client."""
    global _supabase_client
    try:
        _supabase_client = AsyncClient(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        logger.info("Supabase async client initialized with SERVICE_ROLE_KEY")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        raise


async def close_supabase():
    """Close Supabase client."""
    global _supabase_client
    if _supabase_client:
        _supabase_client = None
        logger.info("Supabase client closed")


async def get_supabase_client() -> Any:
    """Get Supabase client."""
    if _supabase_client is None:
        await init_supabase()
    return _supabase_client
