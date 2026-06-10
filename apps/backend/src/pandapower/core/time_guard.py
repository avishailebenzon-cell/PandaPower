"""
Time Guard - Ensures *proactive* outreach only goes out at appropriate times.

Used to gate agent-initiated WhatsApp messages (Tal's opening, Elad's opening,
Elad outreach campaigns) so we never cold-contact a candidate/client on Shabbat,
on a holiday, or at illegitimate hours. Inbound auto-replies are NOT gated — if
someone messages us, we answer.

Schedule (Israel time):
    Sun-Thu  08:00-20:00
    Fri      08:00-13:00
    Sat      blocked
    Holidays blocked
"""

import json
import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (used when no env override is present)
# ---------------------------------------------------------------------------
_DEFAULT_TIMEZONE = "Asia/Jerusalem"

# Allowed outreach window per weekday, as (start_hour, end_hour).
# Python weekday(): Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6.
# None = no outreach allowed that day.
_DEFAULT_WINDOWS: dict[int, tuple[int, int] | None] = {
    0: (8, 20),   # Monday
    1: (8, 20),   # Tuesday
    2: (8, 20),   # Wednesday
    3: (8, 20),   # Thursday
    4: (8, 13),   # Friday — short day, until 13:00
    5: None,      # Saturday — Shabbat, blocked
    6: (8, 20),   # Sunday — working day in Israel
}

# Hebrew holidays when proactive outreach is NOT allowed (month, day).
# NOTE: approximate Gregorian dates — Hebrew holidays drift year to year.
# Review annually. Each tuple blocks the whole civil day in Israel time.
_DEFAULT_HOLIDAYS = {
    (1, 1),   # New Year (Jan 1)
    (3, 18),  # Purim (approximate)
    (4, 8),   # Passover start (approximate)
    (5, 18),  # Lag B'Omer (approximate)
    (5, 28),  # Shavuot (approximate)
    (7, 9),   # Tisha B'Av (approximate)
    (9, 23),  # Rosh Hashanah (approximate)
    (10, 2),  # Yom Kippur (approximate)
    (10, 7),  # Sukkot (approximate)
    (10, 14), # Simchat Torah (approximate)
    (12, 25), # Christmas (Dec 25)
}

_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# JSON schedule keys → Python weekday index.
_DAY_KEYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


# ---------------------------------------------------------------------------
# Env-driven configuration
# ---------------------------------------------------------------------------
def _env_truthy(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _load_config() -> tuple[bool, str, dict[int, tuple[int, int] | None], set[tuple[int, int]]]:
    """Resolve (enabled, timezone, weekday_windows, blocked_holidays) from env.

    Env vars (all optional):
      WHATSAPP_OUTREACH_TIME_GUARD   "false" disables gating entirely (default on)
      WHATSAPP_SENDING_HOURS         JSON: {"timezone": "...",
                                            "schedule": {"sun":[8,20], ..., "sat": null}}
      WHATSAPP_OUTREACH_BLOCKED_DATES  CSV of "MM-DD" days to block (replaces defaults)

    Any parse error falls back to the built-in Israeli defaults — the guard
    fails *closed* (still gates), never silently wide open.
    """
    enabled = _env_truthy(os.getenv("WHATSAPP_OUTREACH_TIME_GUARD"), True)

    timezone = _DEFAULT_TIMEZONE
    windows = dict(_DEFAULT_WINDOWS)
    raw = os.getenv("WHATSAPP_SENDING_HOURS")
    if raw:
        try:
            cfg = json.loads(raw)
            timezone = cfg.get("timezone", _DEFAULT_TIMEZONE)
            schedule = cfg.get("schedule") or {}
            parsed: dict[int, tuple[int, int] | None] = {}
            for key, idx in _DAY_KEYS.items():
                if key not in schedule:
                    parsed[idx] = _DEFAULT_WINDOWS[idx]
                    continue
                val = schedule[key]
                if val is None:
                    parsed[idx] = None
                else:
                    start, end = int(val[0]), int(val[1])
                    parsed[idx] = (start, end)
            windows = parsed
        except Exception as e:
            logger.warning(f"Invalid WHATSAPP_SENDING_HOURS, using defaults: {e}")
            timezone, windows = _DEFAULT_TIMEZONE, dict(_DEFAULT_WINDOWS)

    holidays = set(_DEFAULT_HOLIDAYS)
    raw_dates = os.getenv("WHATSAPP_OUTREACH_BLOCKED_DATES")
    if raw_dates is not None:
        try:
            parsed_dates = set()
            for token in raw_dates.split(","):
                token = token.strip()
                if not token:
                    continue
                mm, dd = token.split("-")
                parsed_dates.add((int(mm), int(dd)))
            holidays = parsed_dates
        except Exception as e:
            logger.warning(f"Invalid WHATSAPP_OUTREACH_BLOCKED_DATES, using defaults: {e}")
            holidays = set(_DEFAULT_HOLIDAYS)

    return enabled, timezone, windows, holidays


def get_current_israel_time() -> datetime:
    """Get current time in the configured outreach timezone."""
    _, timezone, _, _ = _load_config()
    return datetime.now(ZoneInfo(timezone))


def _is_allowed_at(now: datetime) -> tuple[bool, str]:
    """Core check for a given Israel-time datetime."""
    enabled, _, windows, holidays = _load_config()
    if not enabled:
        return True, ""

    if (now.month, now.day) in holidays:
        return False, f"holiday ({now.date().isoformat()})"

    window = windows.get(now.weekday())
    if window is None:
        return False, f"{_DAY_NAMES[now.weekday()]} (blocked day)"

    start, end = window
    if not (time(start, 0) <= now.time() < time(end, 0)):
        return False, (
            f"outside hours {start:02d}:00-{end:02d}:00 on "
            f"{_DAY_NAMES[now.weekday()]} (now {now.time().strftime('%H:%M')})"
        )

    return True, ""


def can_perform_operation(operation_name: str = "outreach") -> tuple[bool, str]:
    """Check if a *proactive* outreach operation may run right now.

    Args:
        operation_name: Name of the operation, for logging.

    Returns:
        (is_allowed, reason_if_blocked)
    """
    allowed, reason = _is_allowed_at(get_current_israel_time())
    if not allowed:
        msg = f"Blocked '{operation_name}': {reason}"
        logger.info(msg)
        return False, msg
    return True, ""


def seconds_until_allowed(max_lookahead_hours: int = 96) -> int:
    """Seconds from now until the next allowed outreach minute.

    Returns 0 if outreach is allowed right now. Steps minute-by-minute up to
    max_lookahead_hours; if nothing opens in that window (shouldn't happen),
    returns that cap so callers can retry rather than wait forever.
    """
    now = get_current_israel_time()
    allowed, _ = _is_allowed_at(now)
    if allowed:
        return 0

    probe = now.replace(second=0, microsecond=0)
    for minutes in range(1, max_lookahead_hours * 60 + 1):
        probe_t = probe + timedelta(minutes=minutes)
        ok, _ = _is_allowed_at(probe_t)
        if ok:
            return int((probe_t - now).total_seconds())
    return max_lookahead_hours * 3600
