import asyncio
import logging
from typing import Any

from supabase import AsyncClient, create_client

from pandapower.core.config import settings

logger = logging.getLogger(__name__)

# Module-level cache plus a reference to the event loop that built the
# client. Under FastAPI/uvicorn there's only ever one loop so the cache
# stays valid forever. Under Celery prefork workers a fresh asyncio loop
# is created per task (asyncio.new_event_loop() → run_until_complete →
# close()), and the cached client's httpx pool is bound to the now-dead
# loop. Reusing it crashes with `RuntimeError: Event loop is closed`.
# Tracking the owning loop and rebuilding when it changes fixes that.
_supabase_client: Any | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _current_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


async def init_supabase():
    """Initialize the Supabase client and remember which event loop it belongs to."""
    global _supabase_client, _client_loop
    try:
        _supabase_client = AsyncClient(
            supabase_url=settings.SUPABASE_URL,
            supabase_key=settings.SUPABASE_SERVICE_ROLE_KEY,
        )
        _client_loop = _current_loop()
        logger.info("Supabase async client initialized with SERVICE_ROLE_KEY")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase: {e}")
        raise


async def close_supabase():
    """Close Supabase client."""
    global _supabase_client, _client_loop
    if _supabase_client:
        _supabase_client = None
        _client_loop = None
        logger.info("Supabase client closed")


async def get_supabase_client() -> Any:
    """Get a Supabase client valid for the current event loop.

    Rebuilds the cached client when called from a fresh event loop, so
    Celery prefork tasks don't reuse a client whose httpx connection
    pool is bound to a closed loop.
    """
    global _supabase_client, _client_loop
    loop = _current_loop()
    if _supabase_client is None or _client_loop is not loop:
        # Drop the stale reference before rebuilding; we don't aclose() it
        # because its loop is already closed — there's nothing live to await.
        _supabase_client = None
        _client_loop = None
        await init_supabase()
    return _supabase_client
