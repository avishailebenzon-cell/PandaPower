#!/usr/bin/env python3
"""
Script to update Pipedrive sync intervals from 4 hours to 12 hours.
This reduces API quota usage from ~500 calls/day to ~165 calls/day.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

async def main():
    from pandapower.core.supabase import get_supabase_client

    db = await get_supabase_client()

    # Update all sync schedules to 720 minutes (12 hours)
    new_interval = 720  # 12 hours in minutes
    now = datetime.now(timezone.utc)
    next_sync = now + timedelta(minutes=new_interval)

    print("Updating Pipedrive sync intervals to 12 hours (720 minutes)...")

    try:
        response = await db.table("pipedrive_sync_schedule").update({
            "sync_interval_minutes": new_interval,
            "next_scheduled_sync": next_sync.isoformat(),
            "updated_at": now.isoformat(),
        }).execute()

        print(f"✅ Updated {len(response.data or [])} sync schedules")

        # Show updated schedules
        schedules = await db.table("pipedrive_sync_schedule").select("*").execute()
        print("\n📊 Updated schedules:")
        for schedule in schedules.data or []:
            entity = schedule.get("entity_type", "unknown")
            interval = schedule.get("sync_interval_minutes", "?")
            status = "✓" if schedule.get("sync_enabled") else "✗"
            print(f"  {status} {entity}: {interval} min ({interval/60:.1f} hours)")

        print("\n💡 Result: ~165 API calls/day (down from ~500)")
        print("📈 That's a 70% reduction in Pipedrive API quota usage!")

        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
