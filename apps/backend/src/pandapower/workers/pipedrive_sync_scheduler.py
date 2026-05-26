"""
Pipedrive Sync Scheduler

Reads user-defined sync settings from the `pipedrive_sync_schedule` table
and decides which entity sync (deals / persons / organizations) should
run right now.

Honors these per-entity settings:
- sync_enabled: only schedules fires when True
- sync_interval_minutes: minimum gap between syncs
- sync_days: list[bool] of length 7 (Sun..Sat). If provided, only those days fire.
- sync_time: "HH:MM" daily start window (if provided, sync only fires after that time)
- last_sync_at: last successful sync timestamp; we won't re-fire before
  last_sync_at + sync_interval_minutes
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string into an aware datetime (UTC)"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _is_due(schedule: Dict[str, Any], now: datetime) -> bool:
    """
    Decide whether the given sync schedule is due to run *right now*.
    """
    # 1) Must be enabled
    if not schedule.get("sync_enabled", False):
        return False

    interval_minutes = int(schedule.get("sync_interval_minutes") or 60)
    if interval_minutes <= 0:
        return False

    # 2) Check sync_days (list of 7 booleans, Sun..Sat)
    sync_days = schedule.get("sync_days")
    if isinstance(sync_days, list) and len(sync_days) == 7:
        # In Python, Monday=0 ... Sunday=6. The frontend stores Sunday=0 ... Saturday=6.
        # Convert: Sunday=0, Mon=1, ..., Sat=6 in our schedule indexing.
        weekday_python = now.weekday()  # Mon=0..Sun=6
        weekday_schedule = (weekday_python + 1) % 7  # Sun=0..Sat=6
        if not bool(sync_days[weekday_schedule]):
            return False

    # 3) Check sync_time (daily start hour:minute window)
    sync_time = schedule.get("sync_time")
    if isinstance(sync_time, str) and ":" in sync_time:
        try:
            hh, mm = sync_time.split(":", 1)
            target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if now < target:
                return False  # Too early today
        except (ValueError, TypeError):
            pass  # Invalid format - ignore the constraint

    # 4) Check interval since last sync
    last_sync = _parse_ts(schedule.get("last_sync_at"))
    if last_sync is not None:
        next_due = last_sync + timedelta(minutes=interval_minutes)
        if now < next_due:
            return False  # Too soon since last run

    return True


async def find_due_schedules(db: Any) -> List[Dict[str, Any]]:
    """Return all sync schedules that are due to run now"""
    try:
        response = await db.table("pipedrive_sync_schedule").select("*").execute()
    except Exception as e:
        logger.error(f"Failed to fetch pipedrive_sync_schedule: {e}")
        return []

    schedules = response.data or []
    now = _now_utc()

    due = [s for s in schedules if _is_due(s, now)]

    if due:
        names = ", ".join(s.get("entity_type", "?") for s in due)
        logger.info(f"Sync scheduler tick: {len(due)} entity(ies) due now ({names})")
    return due


async def mark_schedule_started(db: Any, schedule_id: str) -> None:
    """Optimistically mark a schedule as last_sync_at=now so we don't double-fire"""
    try:
        await db.table("pipedrive_sync_schedule").update({
            "last_sync_at": _now_utc().isoformat(),
            "last_sync_status": "in_progress",
        }).eq("id", schedule_id).execute()
    except Exception as e:
        logger.error(f"Failed to mark schedule {schedule_id} as started: {e}")


async def mark_schedule_completed(
    db: Any,
    schedule_id: str,
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    """Update schedule with final result"""
    now = _now_utc()
    interval_minutes = 60
    try:
        # Fetch interval for computing next_scheduled_sync
        existing = await db.table("pipedrive_sync_schedule").select(
            "sync_interval_minutes, sync_count"
        ).eq("id", schedule_id).single().execute()
        if existing.data:
            interval_minutes = int(existing.data.get("sync_interval_minutes") or 60)
            sync_count = int(existing.data.get("sync_count") or 0)
        else:
            sync_count = 0
    except Exception:
        sync_count = 0

    next_run = now + timedelta(minutes=interval_minutes)
    update_data = {
        "last_sync_at": now.isoformat(),
        "last_sync_status": "completed" if success else "failed",
        "last_sync_error": error_message if not success else None,
        "next_scheduled_sync": next_run.isoformat(),
        "sync_count": sync_count + 1,
    }
    try:
        await db.table("pipedrive_sync_schedule").update(update_data).eq(
            "id", schedule_id
        ).execute()
    except Exception as e:
        logger.error(f"Failed to mark schedule {schedule_id} as completed: {e}")


async def run_due_syncs() -> Dict[str, Any]:
    """
    Main entry point: check all schedules and run those that are due.

    Returns a summary describing which syncs (if any) were triggered.
    """
    from pandapower.core.supabase import get_supabase_client

    db = await get_supabase_client()
    due = await find_due_schedules(db)

    if not due:
        return {"status": "idle", "triggered": []}

    triggered = []

    for schedule in due:
        entity_type = schedule.get("entity_type")
        schedule_id = schedule.get("id")
        if not entity_type or not schedule_id:
            continue

        await mark_schedule_started(db, schedule_id)

        success = False
        error_msg = None
        try:
            if entity_type == "deals":
                from pandapower.workers.pipedrive_deals_sync import sync_pipedrive_deals
                await sync_pipedrive_deals()
            elif entity_type == "persons":
                from pandapower.workers.pipedrive_sync import sync_pipedrive_contacts
                await sync_pipedrive_contacts()
            elif entity_type == "organizations":
                # Organizations are synced as part of contacts sync (pipedrive_sync)
                # because contact->org links require orgs to exist first.
                from pandapower.workers.pipedrive_sync import sync_pipedrive_contacts
                await sync_pipedrive_contacts()
            else:
                logger.warning(f"Unknown entity_type in schedule: {entity_type}")
                continue
            success = True
            triggered.append({"entity": entity_type, "status": "completed"})
            logger.info(f"Scheduled sync completed: {entity_type}")
        except Exception as e:
            error_msg = str(e)
            triggered.append({"entity": entity_type, "status": "failed", "error": error_msg})
            logger.error(f"Scheduled sync failed for {entity_type}: {e}", exc_info=True)

        await mark_schedule_completed(db, schedule_id, success, error_msg)

    return {"status": "ran", "triggered": triggered}
