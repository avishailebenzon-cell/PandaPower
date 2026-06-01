# Telegram Bot — "מנהל גיוס כרמית"

A Telegram bot that lets the admin talk to Carmit and receive proactive alerts,
without opening the web UI.

## What it does

**Conversational (read-only):** ask Carmit in Hebrew about system state, matches,
processes, and problems — she answers from live data. She cannot perform actions
(approve/reject/trigger); those stay in the web UI.

**Proactive push** to the admin's chat:
- 🔔 every match that moves **Carmit → Tal** (candidate + job + score),
- 🎉 every **hire** (match reaching `hired`),
- ⚠️ **process problems** (a stage stalls or fails repeatedly — same events as the
  email alerts, now also in Telegram),
- 📊 a **daily summary** (~09:00 Israel): emails scanned, new matches, handoffs to
  Tal, hires, and any stalled processes.

## One-time setup

1. In Telegram, message **@BotFather** → `/newbot` → copy the **token**.
2. In the admin UI: **🤖 בוט טלגרם — כרמית** → paste the token → **חבר בוט**.
   This validates the token and registers the webhook automatically.
3. Open your new bot in Telegram and send **`/start`** — this binds your chat as
   the admin (only this chat can converse and receives alerts).
4. Click **שלח הודעת בדיקה** to confirm delivery.

## How it works (architecture)

- `integrations/telegram_client.py` — `TelegramClient` (send/setWebhook/getMe) +
  `notify_admin_telegram()` best-effort sender. Config in `system_settings`:
  `telegram.bot_token`, `telegram.admin_chat_id`, `telegram.webhook_secret`,
  `telegram.enabled`.
- **Problem alerts:** `integrations/alert_service.py` `alert_admin()` now also pushes
  to Telegram at its single send choke-point — so every existing pipeline
  failure/crash/stall alert reaches the bot, throttled by the same cooldown.
- **Match→Tal / hire:** scheduler stage `notify_telegram` (every 120s) scans
  `matches` for new `sent_to_tal` / `hired` transitions via an `updated_at`
  watermark (`telegram.notify_watermark`) — fires once per transition, idempotent.
- **Daily summary:** scheduler stage `telegram_daily_summary` (once/day after 06:00
  UTC), guarded by `telegram.last_summary_date`.
- **Conversation:** `POST /webhooks/telegram` verifies Telegram's secret header,
  binds the admin on `/start`, and answers admin messages via Claude using a Carmit
  persona + a live system snapshot (heartbeat health, pipeline counts, totals).
  Heavy work runs in the background so the webhook returns 200 instantly.
- Both new stages appear on the **🩺 ניטור מערכת** dashboard like every other process.

## Notes

- Backend public URL for the webhook comes from `PUBLIC_BASE_URL` (env), defaulting
  to `https://pandapower-backend.onrender.com`.
- The bot is bound to a single admin chat; messages from other chats are ignored.
- To rotate the token, just paste a new one in the UI and re-`/start`.
