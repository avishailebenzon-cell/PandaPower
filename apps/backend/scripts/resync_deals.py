"""Re-sync all deals from Pipedrive with the new full field mapping."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pandapower.core.supabase import init_supabase
from pandapower.workers.pipedrive_deals_sync import sync_pipedrive_deals


async def main():
    await init_supabase()
    result = await sync_pipedrive_deals()
    print("\n" + "=" * 60)
    print("DEALS SYNC RESULT")
    print("=" * 60)
    for key, value in result.items():
        if key == "errors":
            print(f"  {key}: {len(value)} errors")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    asyncio.run(main())
