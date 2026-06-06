"""
Alert Service - sends email notifications to system admins on failures.

Uses Resend (https://resend.com) as the delivery backend. Simpler than the
previous Azure Graph integration: no mailbox permissions, no OAuth dance,
single API key in .env (RESEND_API_KEY).

Design goals:
- Never let a Resend outage cascade into the rest of the pipeline:
  ALL alert-send errors are swallowed (logged, but never raised).
- No alert storms: in-memory dedup + per-key cooldown.
- Configurable admin email via system_settings (no env var redeploy needed).

Usage:
    from pandapower.integrations.alert_service import alert_admin

    try:
        await do_risky_thing()
    except Exception as e:
        await alert_admin(
            key="email-ingest",
            subject="Email ingest failed",
            details=str(e),
            severity="error",
        )
        raise
"""

import asyncio
import json
import logging
import os
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.resend_client import ResendClient, ResendError

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────
# Stored in system_settings - editable via /admin/alerts/config endpoint.
ADMIN_EMAIL_SETTING_KEY = "alerts.admin_email"
ALERTS_ENABLED_SETTING_KEY = "alerts.enabled"
RESEND_FROM_SETTING_KEY = "alerts.resend_from"

# Snooze (global pause) - all alerts suppressed until this wall-clock time.
SNOOZE_UNTIL_SETTING_KEY = "alerts.snooze_until"
# Acknowledged keys (per-alert mute) - JSON map { key: iso_expiry } that survives restarts.
ACK_KEYS_SETTING_KEY = "alerts.acknowledged_keys"

# DB-backed GLOBAL throttle: at most ONE alert (of any key) per this interval.
# Survives process restarts (the in-memory cooldown below does NOT — frequent
# Render redeploys reset it, which is what caused the alert flood). Configurable
# via system_settings 'alerts.min_interval_minutes'.
GLOBAL_LAST_ALERT_SETTING_KEY = "alerts.last_global_alert_at"
GLOBAL_MIN_INTERVAL_SETTING_KEY = "alerts.min_interval_minutes"
DEFAULT_GLOBAL_MIN_INTERVAL_MINUTES = 180  # 3 hours

# Fallback admin email when DB has nothing configured. Set in code so a fresh
# install still notifies the right person.
DEFAULT_ADMIN_EMAIL = "avishai.lebenzon@gmail.com"

# Throttling: never send the same alert key more often than this.
COOLDOWN_SECONDS = 30 * 60  # 30 minutes
# Hard rate limit across ALL alerts to prevent a storm if the throttle fails.
MAX_ALERTS_PER_HOUR = 20


# ── In-memory state (per-process) ────────────────────────────────────────────
# Tracks the last time each alert key was sent.
_last_sent: dict[str, float] = {}
# Sliding window of timestamps for the hard rate limit.
_recent_sends: deque[float] = deque()
_state_lock = asyncio.Lock()


# ── Public API ───────────────────────────────────────────────────────────────


ALERT_CATEGORIES = ("pipeline", "convertapi", "email_ingest", "integrations")
ALERT_CHANNELS = ("email", "telegram")


def category_for_key(key: str) -> str:
    """Map an alert key to a user-toggleable category (keys are dynamic)."""
    k = (key or "").lower()
    if k.startswith("pipeline"):
        return "pipeline"
    if k.startswith("convertapi"):
        return "convertapi"
    if "ingest" in k:
        return "email_ingest"
    return "integrations"


async def alert_admin(
    key: str,
    subject: str,
    details: str,
    severity: str = "error",
    include_traceback: bool = True,
) -> bool:
    """Send an alert to the system admin. Returns True if sent, False if
    suppressed (by throttle / cooldown / disabled / config error).

    `key` uniquely identifies the kind of alert and is used for cooldown.
    Example keys: "email-ingest", "cv-parse-batch", "pipeline-scheduler-crash".
    """
    try:
        # Cooldown check (fast, lock-protected)
        async with _state_lock:
            now = time.monotonic()

            last = _last_sent.get(key)
            if last is not None and (now - last) < COOLDOWN_SECONDS:
                wait = int(COOLDOWN_SECONDS - (now - last))
                logger.debug(
                    f"[alerts] suppressed '{key}' (cooldown, retry in {wait}s)"
                )
                return False

            # Rate limit: drop timestamps older than 1 hour
            cutoff = now - 3600
            while _recent_sends and _recent_sends[0] < cutoff:
                _recent_sends.popleft()
            if len(_recent_sends) >= MAX_ALERTS_PER_HOUR:
                logger.warning(
                    f"[alerts] rate limit hit ({len(_recent_sends)}/hr), dropping '{key}'"
                )
                return False

        # Persistent suppression checks (snooze + acknowledged) - read from DB.
        # We do this OUTSIDE the lock because Supabase calls are slow, and
        # before we reserve a slot in _recent_sends so suppressed alerts don't
        # consume rate-limit budget.
        sb = await get_supabase_client()
        if await _is_globally_snoozed(sb):
            logger.info(f"[alerts] globally snoozed, dropping '{key}'")
            return False
        if await _is_key_acknowledged(sb, key):
            logger.info(f"[alerts] key '{key}' is acknowledged by user, dropping")
            return False
        # DB-backed global throttle (survives restarts): at most one alert of
        # any kind per the configured interval.
        if await _global_throttled(sb):
            logger.info(f"[alerts] global throttle active, dropping '{key}'")
            return False

        # Per-category mute (user toggle in the Alerts settings screen).
        category = category_for_key(key)
        if not await _category_enabled(sb, category):
            logger.info(f"[alerts] category '{category}' disabled, dropping '{key}'")
            return False

        # Reserve a slot now that we know we're really sending
        async with _state_lock:
            _last_sent[key] = now
            _recent_sends.append(now)

        # Compose + send (network is slow, do it outside any lock)
        body = _build_html_body(
            key=key,
            subject=subject,
            details=details,
            severity=severity,
            include_traceback=include_traceback,
        )

        admin_email = await _get_admin_email(sb)
        alerts_enabled = await _alerts_enabled(sb)

        if not alerts_enabled:
            logger.info(f"[alerts] alerts disabled, would have sent '{key}'")
            return False

        # Push to Telegram (best-effort) — only if the telegram channel is on.
        telegram_sent = False
        if await _channel_enabled(sb, "telegram"):
            try:
                from pandapower.integrations.telegram_client import notify_admin_telegram
                _emoji = {"critical": "🔴", "error": "⚠️", "warning": "🟡"}.get(severity, "ℹ️")
                telegram_sent = await notify_admin_telegram(
                    f"{_emoji} <b>בעיה בתהליך</b>\n{subject}\n\n{details}",
                    sb=sb,
                )
            except Exception as e:
                logger.debug(f"[alerts] telegram push failed (non-fatal): {e}")

        # Send via Resend — only if the email channel is on and an address exists.
        sent = False
        if admin_email and await _channel_enabled(sb, "email"):
            sent = await _send_via_resend(
                sb=sb,
                to=admin_email,
                subject=f"[PandaPower {severity.upper()}] {subject}",
                body_html=body,
            )

        if sent or telegram_sent:
            # Record the global send time so the DB-backed throttle holds the
            # next alert for the configured interval (survives restarts).
            await _record_global_alert(sb)
        if sent:
            logger.info(f"[alerts] sent '{key}' to {admin_email}")
        return sent or telegram_sent

    except Exception as e:
        # NEVER propagate alert failures - they would mask the original error
        logger.error(f"[alerts] unexpected failure sending '{key}': {e}", exc_info=True)
        return False


async def send_test_alert(to: Optional[str] = None) -> dict:
    """Send a test alert. Used by the admin UI to verify config.

    Returns a result dict with sent/error info — NEVER raises.
    The error field carries the underlying exception text so the UI can show
    actionable hints (e.g. "Mail.Send permission missing in Azure App").
    """
    try:
        sb = await get_supabase_client()
        recipient = to or await _get_admin_email(sb)
        if not recipient:
            return {"sent": False, "error": "No admin email configured"}

        body = _build_html_body(
            key="manual-test",
            subject="Test alert from PandaPower",
            details=(
                "This is a test alert. If you received this email, your alert "
                "notifications are configured correctly.\n\n"
                "When real failures occur, you will get similar emails describing "
                "what went wrong, when, and how often it has been failing."
            ),
            severity="info",
            include_traceback=False,
        )

        # Call _send_via_resend_raise instead of swallowing errors so we can
        # surface the real Resend error in the UI.
        try:
            await _send_via_resend_raise(
                sb=sb,
                to=recipient,
                subject="[PandaPower INFO] Test alert — please ignore",
                body_html=body,
            )
            return {"sent": True, "recipient": recipient}
        except Exception as send_err:
            return {
                "sent": False,
                "recipient": recipient,
                "error": str(send_err),
            }
    except Exception as e:
        logger.error(f"Test alert failed: {e}", exc_info=True)
        return {"sent": False, "error": str(e)}


# ── Internal helpers ─────────────────────────────────────────────────────────


async def _get_admin_email(sb) -> Optional[str]:
    """Read admin email from system_settings; fall back to DEFAULT_ADMIN_EMAIL."""
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", ADMIN_EMAIL_SETTING_KEY
        ).limit(1).execute()
        if r.data and r.data[0].get("setting_value"):
            val = r.data[0]["setting_value"]
            if isinstance(val, str):
                val = val.strip('"').strip()
            if val and val != "null":
                return val
    except Exception as e:
        logger.debug(f"[alerts] could not read admin email from DB: {e}")
    return DEFAULT_ADMIN_EMAIL


async def _is_globally_snoozed(sb) -> bool:
    """Check if alerts are paused via /admin/alerts/snooze.

    snooze_until stores an ISO timestamp; if it's in the future, suppress all alerts.
    """
    iso = await _read_setting(sb, SNOOZE_UNTIL_SETTING_KEY)
    if not iso:
        return False
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except ValueError:
        return False


async def _is_key_acknowledged(sb, key: str) -> bool:
    """Check if this specific alert key has been muted by the user.

    Acknowledgements live in alerts.acknowledged_keys as a JSON dict
    { key: iso_expiry }. Keys whose expiry passed are ignored (and ideally
    pruned on next /acknowledge call, but lazy is fine).
    """
    raw = await _read_setting(sb, ACK_KEYS_SETTING_KEY)
    if not raw:
        return False
    try:
        ack_map = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(ack_map, dict):
            return False
        iso = ack_map.get(key)
        if not iso:
            return False
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except (ValueError, json.JSONDecodeError):
        return False


async def _read_setting(sb, key: str) -> Optional[str]:
    """Helper: read a single string setting (strips JSON quotes)."""
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", key
        ).limit(1).execute()
        if not r.data:
            return None
        v = r.data[0].get("setting_value")
        if isinstance(v, str):
            v = v.strip('"').strip()
        if not v or v == "null":
            return None
        return v
    except Exception as e:
        logger.debug(f"[alerts] read_setting('{key}') failed: {e}")
        return None


async def _global_min_interval_seconds(sb) -> int:
    """Minimum seconds between ANY two alerts (DB-configurable)."""
    raw = await _read_setting(sb, GLOBAL_MIN_INTERVAL_SETTING_KEY)
    try:
        return int(float(raw)) * 60 if raw else DEFAULT_GLOBAL_MIN_INTERVAL_MINUTES * 60
    except (TypeError, ValueError):
        return DEFAULT_GLOBAL_MIN_INTERVAL_MINUTES * 60


async def _global_throttled(sb) -> bool:
    """True if an alert was sent within the global min-interval. DB-backed, so
    it survives process restarts (unlike the in-memory per-key cooldown)."""
    iso = await _read_setting(sb, GLOBAL_LAST_ALERT_SETTING_KEY)
    if not iso:
        return False
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - dt).total_seconds()
        return elapsed < await _global_min_interval_seconds(sb)
    except ValueError:
        return False


async def _record_global_alert(sb) -> None:
    """Persist 'now' as the last global alert time (upsert)."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = await sb.table("system_settings").select("id").eq(
            "setting_key", GLOBAL_LAST_ALERT_SETTING_KEY
        ).limit(1).execute()
        if existing.data:
            await sb.table("system_settings").update(
                {"setting_value": now_iso}
            ).eq("setting_key", GLOBAL_LAST_ALERT_SETTING_KEY).execute()
        else:
            await sb.table("system_settings").insert(
                {"setting_key": GLOBAL_LAST_ALERT_SETTING_KEY, "setting_value": now_iso}
            ).execute()
    except Exception as e:
        logger.debug(f"[alerts] failed to record global alert time: {e}")


async def _alerts_enabled(sb) -> bool:
    """Check the alerts.enabled toggle. Default ON if missing."""
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", ALERTS_ENABLED_SETTING_KEY
        ).limit(1).execute()
        if r.data and r.data[0].get("setting_value"):
            val = r.data[0]["setting_value"]
            if isinstance(val, str):
                val = val.strip('"').strip().lower()
            if val in ("false", "0", "off", "no", "null"):
                return False
    except Exception as e:
        logger.debug(f"[alerts] could not read alerts_enabled from DB: {e}")
    return True


async def _bool_setting(sb, key: str, default: bool = True) -> bool:
    """Read a boolean system_settings flag. Default ON if missing/unparseable."""
    val = await _read_setting(sb, key)
    if val is None:
        return default
    return str(val).strip().lower() not in ("false", "0", "off", "no", "null")


async def _channel_enabled(sb, channel: str) -> bool:
    """Is this delivery channel (email / telegram) enabled? Default ON."""
    return await _bool_setting(sb, f"alerts.channel.{channel}", default=True)


async def _category_enabled(sb, category: str) -> bool:
    """Is this alert category enabled? Default ON."""
    return await _bool_setting(sb, f"alerts.category.{category}", default=True)


async def _send_via_resend(
    sb,
    to: str,
    subject: str,
    body_html: str,
) -> bool:
    """Send a single email via Resend. Returns True on success.

    Swallows all errors — never raises. Use _send_via_resend_raise() from the
    test endpoint when you want the error text propagated to the UI.
    """
    try:
        await _send_via_resend_raise(sb=sb, to=to, subject=subject, body_html=body_html)
        return True
    except Exception as e:
        logger.error(f"[alerts] Resend send failed: {e}", exc_info=True)
        return False


async def _send_via_resend_raise(
    sb,
    to: str,
    subject: str,
    body_html: str,
) -> None:
    """Send via Resend, propagating errors.

    Reads RESEND_API_KEY from .env (settings.RESEND_API_KEY). Reads the
    optional `from` address from system_settings → alerts.resend_from (falls
    back to the default Resend onboarding sender).
    """
    api_key = settings.RESEND_API_KEY
    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY is not set in .env. Add it from your Resend dashboard "
            "(https://resend.com/api-keys) and restart the backend."
        )

    # Optional: custom verified sender. Defaults to Resend's onboarding sender.
    from_addr = None
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", RESEND_FROM_SETTING_KEY
        ).limit(1).execute()
        if r.data:
            raw = r.data[0].get("setting_value")
            if isinstance(raw, str):
                raw = raw.strip('"').strip()
            if raw and raw != "null":
                from_addr = raw
    except Exception:
        pass  # fall back to default

    client = ResendClient(api_key=api_key)
    try:
        await client.send_email(
            to=to, subject=subject, html=body_html, from_addr=from_addr
        )
    finally:
        await client.close()


def _build_html_body(
    key: str,
    subject: str,
    details: str,
    severity: str,
    include_traceback: bool,
) -> str:
    """Render an HTML email body. Includes traceback automatically if available."""
    color = {
        "info": "#3b82f6",      # blue
        "warning": "#f59e0b",   # amber
        "error": "#ef4444",     # red
        "critical": "#991b1b",  # dark red
    }.get(severity, "#6b7280")

    tb_html = ""
    if include_traceback:
        tb = traceback.format_exc()
        # If there's an active exception we'll include it; else format_exc returns "NoneType: None\n"
        if tb and "NoneType: None" not in tb:
            tb_html = (
                f"<h4 style='margin-top:24px;color:#374151;'>Traceback</h4>"
                f"<pre style='background:#f3f4f6;padding:12px;border-radius:6px;"
                f"overflow-x:auto;font-size:11px;line-height:1.4;color:#111827;"
                f"white-space:pre-wrap;word-wrap:break-word;'>{_escape(tb)}</pre>"
            )

    env_label = os.getenv("ENVIRONMENT", "development")

    return f"""\
<!DOCTYPE html>
<html lang="en"><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:0;padding:0;background:#f9fafb;">
<div style="max-width:640px;margin:0 auto;padding:24px;">
  <div style="background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;box-shadow:0 4px 6px rgba(0,0,0,0.04);">
    <div style="background:{color};padding:16px 24px;color:#fff;">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;opacity:0.9;">{severity}</div>
      <div style="font-size:20px;font-weight:600;margin-top:4px;">{_escape(subject)}</div>
    </div>
    <div style="padding:24px;">
      <table style="width:100%;font-size:12px;color:#6b7280;margin-bottom:16px;">
        <tr><td style="padding:2px 0;"><b>Alert key:</b></td><td style="font-family:monospace;color:#111827;">{_escape(key)}</td></tr>
        <tr><td style="padding:2px 0;"><b>Environment:</b></td><td style="font-family:monospace;color:#111827;">{_escape(env_label)}</td></tr>
        <tr><td style="padding:2px 0;"><b>Cooldown:</b></td><td>{COOLDOWN_SECONDS // 60} minutes before next alert for this key</td></tr>
      </table>
      <h4 style="margin-top:0;color:#374151;">Details</h4>
      <div style="background:#f9fafb;padding:16px;border-radius:6px;border-left:3px solid {color};white-space:pre-wrap;font-size:13px;line-height:1.6;color:#1f2937;">{_escape(details)}</div>
      {tb_html}
    </div>
    <div style="background:#f9fafb;padding:12px 24px;border-top:1px solid #e5e7eb;font-size:11px;color:#9ca3af;">
      📨 Sent by PandaPower AlertService. To stop these emails, disable alerts at
      <code>/admin/alerts</code>.
    </div>
  </div>
</div>
</body></html>"""


def _escape(text: str) -> str:
    """Minimal HTML-escape so error messages with <, >, & don't break rendering."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
