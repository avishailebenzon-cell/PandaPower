"""Telegram Bot API client + admin notification helper.

Used by the "מנהל גיוס כרמית" bot:
  • TelegramClient — thin async wrapper over api.telegram.org (send/setWebhook/getMe).
  • notify_admin_telegram — best-effort push of a message to the admin's chat,
    reading the bot token + chat id from system_settings. NEVER raises, so it's
    safe to call from notification hooks / the alert choke-point.

Settings keys (system_settings):
  telegram.bot_token       - BotFather token
  telegram.admin_chat_id   - chat id bound on first /start
  telegram.webhook_secret  - X-Telegram-Bot-Api-Secret-Token value
  telegram.enabled         - "true"/"false" (defaults to enabled if a token exists)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"

# Telegram hard-caps message text at 4096 chars.
_MAX_TEXT = 4000


class TelegramClient:
    """Minimal async Telegram Bot API client (mirrors the httpx pattern used in
    integrations/pipedrive_client.py)."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.bot_token}/{method}"

    async def send_message(
        self, chat_id: str | int, text: str, parse_mode: Optional[str] = "HTML"
    ) -> dict[str, Any]:
        """Send a text message. Truncates to Telegram's limit. Raises on non-2xx."""
        client = await self._get_client()
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:_MAX_TEXT],
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = await client.post(self._url("sendMessage"), json=payload)
        if resp.status_code >= 400:
            # HTML parse errors are common; retry once as plain text so a stray
            # '<' never silently drops an important notification.
            if parse_mode:
                payload.pop("parse_mode", None)
                resp = await client.post(self._url("sendMessage"), json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"Telegram sendMessage {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def set_webhook(self, url: str, secret_token: str) -> dict[str, Any]:
        """Register the webhook URL + secret with Telegram."""
        client = await self._get_client()
        resp = await client.post(
            self._url("setWebhook"),
            json={
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            },
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Telegram setWebhook {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    async def get_webhook_info(self) -> dict[str, Any]:
        client = await self._get_client()
        resp = await client.get(self._url("getWebhookInfo"))
        return resp.json()

    async def get_me(self) -> dict[str, Any]:
        """Return bot identity (used to confirm the token works)."""
        client = await self._get_client()
        resp = await client.get(self._url("getMe"))
        if resp.status_code >= 400:
            raise RuntimeError(f"Telegram getMe {resp.status_code}: {resp.text[:300]}")
        return resp.json()


# ---------------------------------------------------------------------------
# Settings helpers (system_settings) — values are stored as plain strings.
# ---------------------------------------------------------------------------

async def _read_setting(sb, key: str) -> Optional[str]:
    try:
        r = await sb.table("system_settings").select("setting_value").eq(
            "setting_key", key
        ).limit(1).execute()
        if r.data and r.data[0].get("setting_value") is not None:
            val = r.data[0]["setting_value"]
            if isinstance(val, str):
                val = val.strip().strip('"').strip()
            if val and val != "null":
                return val
    except Exception as e:
        logger.debug(f"[telegram] could not read setting {key}: {e}")
    return None


async def get_telegram_config(sb) -> dict[str, Optional[str]]:
    """Read all telegram.* settings at once."""
    out: dict[str, Optional[str]] = {
        "bot_token": None,
        "admin_chat_id": None,
        "webhook_secret": None,
        "enabled": None,
    }
    try:
        r = await sb.table("system_settings").select(
            "setting_key, setting_value"
        ).like("setting_key", "telegram.%").execute()
        for row in (r.data or []):
            field = (row.get("setting_key") or "").split(".", 1)[-1]
            val = row.get("setting_value")
            if isinstance(val, str):
                val = val.strip().strip('"').strip()
            if field in out:
                out[field] = val or None
    except Exception as e:
        logger.debug(f"[telegram] could not read config: {e}")
    return out


async def notify_admin_telegram(text: str, sb=None) -> bool:
    """Best-effort send of `text` to the admin's Telegram chat.

    Returns True if a message was sent, False otherwise. NEVER raises — safe to
    call from the alert choke-point and from notification hooks. No-op (returns
    False) if the bot isn't configured / no chat bound / disabled.
    """
    try:
        if sb is None:
            from pandapower.core.supabase import get_supabase_client
            sb = await get_supabase_client()

        cfg = await get_telegram_config(sb)
        token = cfg.get("bot_token")
        chat_id = cfg.get("admin_chat_id")
        enabled = (cfg.get("enabled") or "true").lower() != "false"

        if not token or not chat_id or not enabled:
            logger.debug("[telegram] notify skipped (not configured / disabled)")
            return False

        client = TelegramClient(token)
        try:
            await client.send_message(chat_id, text)
            return True
        finally:
            await client.close()
    except Exception as e:
        logger.warning(f"[telegram] notify_admin_telegram failed (non-fatal): {e}")
        return False
