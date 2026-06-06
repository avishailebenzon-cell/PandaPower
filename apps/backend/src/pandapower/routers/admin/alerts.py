"""
Admin endpoints for managing system alert notifications.

The admin can:
- View / update the admin email address
- Enable/disable alerts
- Send a test alert to verify Azure mail is working
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import re

from pydantic import BaseModel, field_validator

from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.alert_service import (
    ACK_KEYS_SETTING_KEY,
    ADMIN_EMAIL_SETTING_KEY,
    ALERTS_ENABLED_SETTING_KEY,
    ALERT_CATEGORIES,
    ALERT_CHANNELS,
    COOLDOWN_SECONDS,
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_GLOBAL_MIN_INTERVAL_MINUTES,
    GLOBAL_MIN_INTERVAL_SETTING_KEY,
    MAX_ALERTS_PER_HOUR,
    SNOOZE_UNTIL_SETTING_KEY,
    _bool_setting,
    _last_sent,
    _read_setting,
    _recent_sends,
    send_test_alert,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/alerts", tags=["admin", "alerts"])


_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _validate_email(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not _EMAIL_RE.match(v):
        raise ValueError(f"Invalid email address: {v!r}")
    return v


class AlertsConfig(BaseModel):
    admin_email: str
    enabled: bool


class UpdateAlertsConfig(BaseModel):
    admin_email: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("admin_email")
    @classmethod
    def _check_email(cls, v):
        return _validate_email(v)


# Human-readable labels for the per-category toggles (shown in the UI).
CATEGORY_LABELS = {
    "pipeline": "תקלות פייפליין (שלבי עיבוד)",
    "convertapi": "ConvertAPI (מכסת המרות)",
    "email_ingest": "קליטת מיילים",
    "integrations": "אינטגרציות (Anthropic / Azure / Pipedrive / Supabase)",
}
CHANNEL_LABELS = {"email": "מייל", "telegram": "בוט טלגרם"}


class AlertPreferences(BaseModel):
    enabled: bool                       # master switch
    min_interval_minutes: int           # global throttle
    channels: dict[str, bool]           # {email, telegram}
    categories: dict[str, bool]         # {pipeline, convertapi, ...}
    channel_labels: dict[str, str]
    category_labels: dict[str, str]


class UpdateAlertPreferences(BaseModel):
    enabled: Optional[bool] = None
    min_interval_minutes: Optional[int] = None
    channels: Optional[dict[str, bool]] = None
    categories: Optional[dict[str, bool]] = None


class TestAlertResponse(BaseModel):
    sent: bool
    recipient: Optional[str] = None
    error: Optional[str] = None


class AcknowledgedKey(BaseModel):
    key: str
    expires_at: str  # ISO 8601


class AlertsStatus(BaseModel):
    admin_email: str
    enabled: bool
    cooldown_minutes: int
    max_alerts_per_hour: int
    recent_alerts_count: int
    active_cooldowns: list[dict]
    snoozed_until: Optional[str] = None  # ISO; null when not snoozed
    acknowledged_keys: list[AcknowledgedKey] = []


class SnoozeRequest(BaseModel):
    """Pause ALL alerts for `minutes`. If minutes <= 0, treat as 'until manually resumed'."""
    minutes: int  # 0 or negative means infinity (until /unsnooze)


class AcknowledgeRequest(BaseModel):
    """Mute one specific alert key for `minutes`. Use minutes=0 for 'until cleared by user'."""
    key: str
    minutes: int  # 0 means until manually unacknowledged

    @field_validator("key")
    @classmethod
    def _check_key(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("key must not be empty")
        return v


# Effectively-infinite expiry for "until manually cleared". 100 years from now
# is plenty - we'll be long retired by the time it expires.
_FOREVER_SECONDS = 100 * 365 * 24 * 3600


async def _upsert_setting(sb, key: str, value: str) -> None:
    """UPSERT a single system_settings row (no UNIQUE constraint, so check-then-write)."""
    existing = await sb.table("system_settings").select("setting_key").eq(
        "setting_key", key
    ).limit(1).execute()
    payload = {
        "setting_key": key,
        "setting_value": value,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if existing.data:
        await sb.table("system_settings").update(payload).eq(
            "setting_key", key
        ).execute()
    else:
        await sb.table("system_settings").insert(payload).execute()


@router.get("/config", response_model=AlertsConfig)
async def get_config(sb=Depends(get_supabase_client)) -> AlertsConfig:
    """Read the current alert config (admin email + enabled flag)."""
    try:
        rows = await sb.table("system_settings").select(
            "setting_key, setting_value"
        ).in_(
            "setting_key",
            [ADMIN_EMAIL_SETTING_KEY, ALERTS_ENABLED_SETTING_KEY],
        ).execute()

        admin_email = DEFAULT_ADMIN_EMAIL
        enabled = True
        for row in rows.data or []:
            k = row["setting_key"]
            v = row.get("setting_value")
            if isinstance(v, str):
                v = v.strip('"').strip()
            if k == ADMIN_EMAIL_SETTING_KEY and v and v != "null":
                admin_email = v
            elif k == ALERTS_ENABLED_SETTING_KEY:
                enabled = v not in ("false", "0", "off", "no", "null")

        return AlertsConfig(admin_email=admin_email, enabled=enabled)

    except Exception as e:
        logger.error(f"Failed to read alerts config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config", response_model=AlertsConfig)
async def update_config(
    update: UpdateAlertsConfig,
    sb=Depends(get_supabase_client),
) -> AlertsConfig:
    """Update admin email and/or enabled flag. Partial updates supported."""
    try:
        if update.admin_email is not None:
            await _upsert_setting(sb, ADMIN_EMAIL_SETTING_KEY, f'"{update.admin_email}"')

        if update.enabled is not None:
            await _upsert_setting(
                sb, ALERTS_ENABLED_SETTING_KEY,
                "true" if update.enabled else "false",
            )

        # Return the updated config so the UI can immediately reflect it.
        return await get_config(sb)

    except Exception as e:
        logger.error(f"Failed to update alerts config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences", response_model=AlertPreferences)
async def get_preferences(sb=Depends(get_supabase_client)) -> AlertPreferences:
    """Granular alert toggles: master switch, throttle interval, per-channel
    (email/telegram) and per-category mutes. All default ON."""
    enabled = await _bool_setting(sb, ALERTS_ENABLED_SETTING_KEY, default=True)
    raw_interval = await _read_setting(sb, GLOBAL_MIN_INTERVAL_SETTING_KEY)
    try:
        interval = int(float(raw_interval)) if raw_interval else DEFAULT_GLOBAL_MIN_INTERVAL_MINUTES
    except (TypeError, ValueError):
        interval = DEFAULT_GLOBAL_MIN_INTERVAL_MINUTES
    channels = {c: await _bool_setting(sb, f"alerts.channel.{c}", True) for c in ALERT_CHANNELS}
    categories = {c: await _bool_setting(sb, f"alerts.category.{c}", True) for c in ALERT_CATEGORIES}
    return AlertPreferences(
        enabled=enabled,
        min_interval_minutes=interval,
        channels=channels,
        categories=categories,
        channel_labels=CHANNEL_LABELS,
        category_labels=CATEGORY_LABELS,
    )


@router.post("/preferences", response_model=AlertPreferences)
async def update_preferences(
    update: UpdateAlertPreferences,
    sb=Depends(get_supabase_client),
) -> AlertPreferences:
    """Partial update of the granular alert toggles."""
    try:
        if update.enabled is not None:
            await _upsert_setting(sb, ALERTS_ENABLED_SETTING_KEY,
                                  "true" if update.enabled else "false")
        if update.min_interval_minutes is not None:
            iv = max(0, int(update.min_interval_minutes))
            await _upsert_setting(sb, GLOBAL_MIN_INTERVAL_SETTING_KEY, str(iv))
        for ch, on in (update.channels or {}).items():
            if ch in ALERT_CHANNELS:
                await _upsert_setting(sb, f"alerts.channel.{ch}", "true" if on else "false")
        for cat, on in (update.categories or {}).items():
            if cat in ALERT_CATEGORIES:
                await _upsert_setting(sb, f"alerts.category.{cat}", "true" if on else "false")
        return await get_preferences(sb)
    except Exception as e:
        logger.error(f"Failed to update alert preferences: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test", response_model=TestAlertResponse)
async def send_test(to: Optional[str] = None) -> TestAlertResponse:
    """Send a test alert. If `to` is omitted, uses the configured admin email."""
    if to is not None:
        try:
            to = _validate_email(to)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    result = await send_test_alert(to=to)
    return TestAlertResponse(**result)


@router.get("/status", response_model=AlertsStatus)
async def get_status(sb=Depends(get_supabase_client)) -> AlertsStatus:
    """Diagnostics: current config + which alert keys are currently in cooldown."""
    import time

    cfg = await get_config(sb)

    now_mono = time.monotonic()
    cooldowns = []
    for key, last in _last_sent.items():
        remaining = COOLDOWN_SECONDS - (now_mono - last)
        if remaining > 0:
            cooldowns.append({
                "key": key,
                "remaining_seconds": int(remaining),
            })

    # Snooze + acknowledged are persisted in system_settings.
    snooze_until = await _read_snooze_until(sb)
    ack_keys = await _read_acknowledged_keys(sb)

    return AlertsStatus(
        admin_email=cfg.admin_email,
        enabled=cfg.enabled,
        cooldown_minutes=COOLDOWN_SECONDS // 60,
        max_alerts_per_hour=MAX_ALERTS_PER_HOUR,
        recent_alerts_count=len(_recent_sends),
        active_cooldowns=cooldowns,
        snoozed_until=snooze_until,
        acknowledged_keys=[
            AcknowledgedKey(key=k, expires_at=v) for k, v in ack_keys.items()
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Snooze (global pause) + Acknowledge (per-key mute)
# ─────────────────────────────────────────────────────────────────────────────


async def _read_snooze_until(sb) -> Optional[str]:
    """Return the ISO timestamp until which alerts are globally paused, or None."""
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", SNOOZE_UNTIL_SETTING_KEY
        ).limit(1).execute()
        if not r.data:
            return None
        v = r.data[0].get("setting_value")
        if isinstance(v, str):
            v = v.strip('"').strip()
        if not v or v == "null":
            return None
        # If the stored timestamp is already in the past, it's effectively cleared.
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
        return v
    except Exception:
        return None


async def _read_acknowledged_keys(sb) -> dict[str, str]:
    """Return {key: iso_expiry} for all currently-acknowledged alert keys.

    Expired entries are filtered out (and pruned next time someone calls
    /acknowledge so the dict doesn't grow without bound).
    """
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", ACK_KEYS_SETTING_KEY
        ).limit(1).execute()
        if not r.data:
            return {}
        v = r.data[0].get("setting_value")
        if isinstance(v, str):
            v = v.strip('"').strip()
        if not v or v == "null":
            return {}
        try:
            ack_map = json.loads(v)
        except json.JSONDecodeError:
            return {}
        if not isinstance(ack_map, dict):
            return {}

        # Filter out expired keys
        now = datetime.now(timezone.utc)
        active = {}
        for k, iso in ack_map.items():
            try:
                dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt > now:
                    active[k] = iso
            except ValueError:
                pass
        return active
    except Exception:
        return {}


@router.post("/snooze")
async def snooze_all(
    req: SnoozeRequest, sb=Depends(get_supabase_client)
) -> dict:
    """Pause ALL alerts for `minutes` minutes.

    `minutes <= 0` means "until manually resumed" - we store a far-future date.
    """
    minutes = req.minutes
    if minutes <= 0:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=_FOREVER_SECONDS)
        label = "indefinite"
    else:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        label = f"{minutes} minute(s)"

    iso = expiry.isoformat()
    await _upsert_setting(sb, SNOOZE_UNTIL_SETTING_KEY, f'"{iso}"')
    return {"status": "snoozed", "until": iso, "duration": label}


@router.post("/unsnooze")
async def unsnooze_all(sb=Depends(get_supabase_client)) -> dict:
    """Resume alert delivery (cancels any active snooze)."""
    await _upsert_setting(sb, SNOOZE_UNTIL_SETTING_KEY, "null")
    return {"status": "resumed"}


@router.post("/acknowledge")
async def acknowledge_key(
    req: AcknowledgeRequest, sb=Depends(get_supabase_client)
) -> dict:
    """Mute one specific alert key (e.g. 'pipeline-ingest-repeated-failures').

    Use when the user has SEEN the problem and doesn't want repeated emails
    about it until they actively fix it. `minutes=0` means "until I unmute".
    """
    if req.minutes <= 0:
        expiry = datetime.now(timezone.utc) + timedelta(seconds=_FOREVER_SECONDS)
        label = "indefinite"
    else:
        expiry = datetime.now(timezone.utc) + timedelta(minutes=req.minutes)
        label = f"{req.minutes} minute(s)"

    iso = expiry.isoformat()
    current = await _read_acknowledged_keys(sb)  # already-filtered (expired purged)
    current[req.key] = iso

    await _upsert_setting(sb, ACK_KEYS_SETTING_KEY, json.dumps(current))
    return {
        "status": "acknowledged",
        "key": req.key,
        "until": iso,
        "duration": label,
        "total_acknowledged": len(current),
    }


@router.post("/unacknowledge")
async def unacknowledge_key(
    req: AcknowledgeRequest, sb=Depends(get_supabase_client)
) -> dict:
    """Re-enable alerts for a previously-acknowledged key."""
    current = await _read_acknowledged_keys(sb)
    if req.key not in current:
        return {"status": "not_found", "key": req.key, "total_acknowledged": len(current)}
    current.pop(req.key, None)
    await _upsert_setting(sb, ACK_KEYS_SETTING_KEY, json.dumps(current) if current else "null")
    return {"status": "cleared", "key": req.key, "total_acknowledged": len(current)}
