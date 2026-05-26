"""
Time Guard - Ensures operations only happen during appropriate times.
Prevents sending messages/invites to users outside business hours.
"""

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Configuration for allowed operation times
BUSINESS_HOURS_START = time(8, 0)  # 8:00 AM
BUSINESS_HOURS_END = time(20, 0)    # 8:00 PM
TIMEZONE = "Asia/Jerusalem"  # Israel timezone

# Days when operations are NOT allowed (0=Monday, 6=Sunday)
BLOCKED_WEEKDAYS = {5, 6}  # Saturday (5) and Sunday (6)

# Hebrew holidays when operations are NOT allowed (month, day)
# These are approximate dates for major holidays
BLOCKED_HOLIDAYS = {
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


def get_current_israel_time() -> datetime:
    """Get current time in Israel timezone."""
    return datetime.now(ZoneInfo(TIMEZONE))


def is_business_hours() -> bool:
    """
    Check if current time is within business hours.

    Returns:
        bool: True if within business hours, False otherwise
    """
    now = get_current_israel_time()
    current_time = now.time()

    # Check if current time is within business hours
    if not (BUSINESS_HOURS_START <= current_time <= BUSINESS_HOURS_END):
        logger.warning(
            f"Operation attempted outside business hours: {current_time.isoformat()}"
        )
        return False

    return True


def is_allowed_weekday() -> bool:
    """
    Check if today is a working day (not Saturday or Sunday).

    Returns:
        bool: True if weekday (Mon-Fri), False if weekend
    """
    now = get_current_israel_time()
    weekday = now.weekday()

    if weekday in BLOCKED_WEEKDAYS:
        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][weekday]
        logger.warning(f"Operation attempted on {day_name} (weekend)")
        return False

    return True


def is_allowed_holiday() -> bool:
    """
    Check if today is NOT a blocked holiday.

    Returns:
        bool: True if not a blocked holiday, False if blocked
    """
    now = get_current_israel_time()
    today_tuple = (now.month, now.day)

    if today_tuple in BLOCKED_HOLIDAYS:
        logger.warning(f"Operation attempted on blocked holiday: {now.date().isoformat()}")
        return False

    return True


def can_perform_operation(operation_name: str = "user interaction") -> tuple[bool, str]:
    """
    Check if an operation can be performed at the current time.
    This is a safety guard to prevent sending messages/invites to users
    at inappropriate times.

    Args:
        operation_name: Name of the operation for logging

    Returns:
        tuple: (is_allowed, reason_if_blocked)
    """
    # Check business hours
    if not is_business_hours():
        now = get_current_israel_time()
        reason = (
            f"Cannot perform '{operation_name}' outside business hours "
            f"({BUSINESS_HOURS_START.isoformat()}-{BUSINESS_HOURS_END.isoformat()}). "
            f"Current time: {now.time().isoformat()}"
        )
        return False, reason

    # Check weekday
    if not is_allowed_weekday():
        now = get_current_israel_time()
        day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]
        reason = f"Cannot perform '{operation_name}' on weekends. Today is {day_name}."
        return False, reason

    # Check holidays
    if not is_allowed_holiday():
        now = get_current_israel_time()
        reason = f"Cannot perform '{operation_name}' on blocked holidays. Today is {now.date().isoformat()}."
        return False, reason

    logger.info(f"Operation '{operation_name}' allowed at {get_current_israel_time().isoformat()}")
    return True, ""


def log_operation_time(operation_name: str, user_id: str, details: dict = None) -> None:
    """
    Log when an operation was performed, for audit trail.

    Args:
        operation_name: Name of operation (e.g., "generate_invite", "send_message")
        user_id: User who initiated the operation
        details: Additional details to log
    """
    now = get_current_israel_time()
    log_entry = {
        "timestamp": now.isoformat(),
        "operation": operation_name,
        "user_id": user_id,
        "details": details or {},
    }
    logger.info(f"Operation log: {log_entry}")
