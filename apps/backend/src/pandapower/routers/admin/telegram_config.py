"""Admin config for the Telegram bot ("מנהל גיוס כרמית").

Endpoints:
  POST /admin/telegram/configure  - save bot token, register webhook + secret
  GET  /admin/telegram/status     - current config / webhook / binding state
  POST /admin/telegram/test       - send a test message to the bound admin chat
"""

import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.telegram_client import (
    TelegramClient,
    get_telegram_config,
    notify_admin_telegram,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/telegram", tags=["admin-telegram"])

# Public base URL of THIS backend (where Telegram should POST updates).
DEFAULT_PUBLIC_BASE_URL = "https://pandapower-backend.onrender.com"


def _public_base_url() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).rstrip("/")


async def _upsert(sb, key: str, value: str) -> None:
    await sb.table("system_settings").upsert(
        {"setting_key": key, "setting_value": value, "updated_at": datetime.utcnow().isoformat()},
        on_conflict="setting_key",
    ).execute()


class ConfigureRequest(BaseModel):
    bot_token: str


@router.post("/configure")
async def configure(request: ConfigureRequest) -> dict:
    """Store the BotFather token, generate a webhook secret, and register the
    webhook with Telegram. Returns the bot username on success."""
    token = (request.bot_token or "").strip()
    if not token or ":" not in token:
        raise HTTPException(status_code=400, detail="Invalid bot token")

    sb = await get_supabase_client()
    client = TelegramClient(token)
    try:
        # Validate token
        me = await client.get_me()
        if not me.get("ok"):
            raise HTTPException(status_code=400, detail=f"Telegram rejected token: {me}")
        username = (me.get("result") or {}).get("username")

        # Generate + register webhook
        secret = secrets.token_urlsafe(24)
        webhook_url = f"{_public_base_url()}/webhooks/telegram"
        hook = await client.set_webhook(webhook_url, secret)
        if not hook.get("ok"):
            raise HTTPException(status_code=400, detail=f"setWebhook failed: {hook}")

        # Persist settings (token, secret, enabled). admin_chat_id binds on /start.
        await _upsert(sb, "telegram.bot_token", token)
        await _upsert(sb, "telegram.webhook_secret", secret)
        await _upsert(sb, "telegram.enabled", "true")

        return {
            "status": "configured",
            "bot_username": username,
            "webhook_url": webhook_url,
            "next_step": "שלח /start לבוט בטלגרם כדי לשייך את הצ'אט שלך לקבלת התראות.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Telegram configure failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await client.close()


@router.get("/status")
async def status() -> dict:
    """Report current Telegram bot configuration state."""
    sb = await get_supabase_client()
    cfg = await get_telegram_config(sb)
    configured = bool(cfg.get("bot_token"))
    bound = bool(cfg.get("admin_chat_id"))
    enabled = (cfg.get("enabled") or "true").lower() != "false"

    bot_username = None
    webhook_ok = None
    if configured:
        client = TelegramClient(cfg["bot_token"])
        try:
            me = await client.get_me()
            bot_username = (me.get("result") or {}).get("username")
            info = await client.get_webhook_info()
            webhook_ok = bool((info.get("result") or {}).get("url"))
        except Exception as e:
            logger.debug(f"telegram status probe failed: {e}")
        finally:
            await client.close()

    return {
        "configured": configured,
        "enabled": enabled,
        "admin_chat_bound": bound,
        "bot_username": bot_username,
        "webhook_registered": webhook_ok,
    }


@router.post("/test")
async def send_test() -> dict:
    """Send a test message to the bound admin chat."""
    sb = await get_supabase_client()
    cfg = await get_telegram_config(sb)
    if not cfg.get("bot_token"):
        raise HTTPException(status_code=400, detail="Bot not configured")
    if not cfg.get("admin_chat_id"):
        raise HTTPException(status_code=400, detail="No admin chat bound — send /start to the bot first")

    ok = await notify_admin_telegram(
        "✅ בדיקה: הבוט של כרמית מחובר ועובד. מכאן תקבל התראות על התאמות, גיוסים ותקלות.",
        sb=sb,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send test message")
    return {"status": "sent"}
