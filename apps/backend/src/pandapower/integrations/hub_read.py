"""
Read mirrored Pipedrive data from the central Hub (a separate Supabase project
synced once daily) instead of calling the Pipedrive API.

Used by the bulk sync workers behind the USE_HUB_READS flag. Returns the full
Pipedrive payloads (pd_*.raw), which have the exact same shape get_all_persons /
get_all_deals / get_all_organizations return from the live API — so the existing
mappers in pipedrive_sync.py / pipedrive_deals_sync.py work unchanged.

Writes (Dana/Pandi/Pandius create_person/deal/note) stay direct to Pipedrive.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from supabase import AsyncClient

logger = logging.getLogger(__name__)

USE_HUB_READS = os.getenv("USE_HUB_READS", "false").lower() == "true"

_hub_client: Optional[AsyncClient] = None


def _get_hub() -> AsyncClient:
    global _hub_client
    if _hub_client is None:
        url = os.getenv("HUB_SUPABASE_URL")
        key = os.getenv("HUB_SUPABASE_KEY")  # anon or service-role key of the Hub
        if not url or not key:
            raise RuntimeError(
                "USE_HUB_READS is on but HUB_SUPABASE_URL / HUB_SUPABASE_KEY are not set"
            )
        _hub_client = AsyncClient(supabase_url=url, supabase_key=key)
        logger.info("Hub client initialized (reads served from Pipedrive Hub)")
    return _hub_client


async def _fetch_raw(table: str, since: Optional[datetime]) -> list:
    """Page through `table`, returning the list of `raw` payloads. If `since` is
    given, only rows whose Pipedrive update time is newer are returned."""
    hub = _get_hub()
    page_size = 1000
    out: list = []
    start = 0
    while True:
        query = hub.table(table).select("raw")
        if since is not None:
            query = query.gte("pd_update_time", since.isoformat())
        resp = await query.range(start, start + page_size - 1).execute()
        rows = resp.data or []
        out.extend(r["raw"] for r in rows if r.get("raw") is not None)
        if len(rows) < page_size:
            break
        start += page_size
    logger.info(f"Fetched {len(out)} rows from Hub.{table}")
    return out


async def get_all_persons_from_hub(since: Optional[datetime] = None) -> list:
    return await _fetch_raw("pd_persons", since)


async def get_all_deals_from_hub(since: Optional[datetime] = None) -> list:
    return await _fetch_raw("pd_deals", since)


async def get_all_organizations_from_hub(since: Optional[datetime] = None) -> list:
    return await _fetch_raw("pd_organizations", since)


async def get_deal_notes_from_hub(deal_id) -> list:
    """Return the raw Pipedrive note payloads linked to a deal, from the Hub mirror."""
    hub = _get_hub()
    resp = await hub.table("pd_notes").select("raw").eq("deal_id", deal_id).execute()
    return [r["raw"] for r in (resp.data or []) if r.get("raw") is not None]
