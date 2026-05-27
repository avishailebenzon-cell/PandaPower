"""WhatsApp-agents settings — Tal / Elad / Pandi Green-API credentials.

These three agents each have their own Green-API instance (separate
phone number, separate token, separate webhook secret). The Green-API
client factory at integrations/green_api.py:get_green_api_client()
reads the per-agent credentials out of the `system_settings` key-value
table using keys like `pandi.instance_id`, `pandi.token`, etc.

This router gives the frontend a clean way to read and write those
settings, strictly separated per agent — there is no shared field,
and saves to one agent never touch another's row.

Endpoints:
    GET  /admin/whatsapp-agents/config              -> all 3 agents
    GET  /admin/whatsapp-agents/{agent_code}/config -> one agent
    POST /admin/whatsapp-agents/{agent_code}/config -> upsert one agent

Security note: tokens and webhook secrets are returned in plain text to
the admin UI; this is an internal-only tool with auto-admin auth (see
useAuth.ts). When public auth is added, mask these on the GET response.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/whatsapp-agents", tags=["admin", "whatsapp"])


# The fixed set of agents that have a WhatsApp presence. Adding a new one
# here is the single source of truth — the UI iterates over these.
SUPPORTED_AGENTS = ("tal", "elad", "pandi")
AgentCode = Literal["tal", "elad", "pandi"]

# The four fields per agent. Keys are namespaced "{agent}.{field}" in
# system_settings (matching what integrations/green_api.py reads).
FIELD_KEYS = ("instance_id", "token", "whatsapp_number", "webhook_secret")


AGENT_LABELS = {
    "tal": {"name": "טל", "role": "סוכן ראשוני (שיחה עם מועמד)", "emoji": "👩‍💼"},
    "elad": {"name": "אלעד", "role": "הצבות (שיחה עם לקוח)", "emoji": "🤝"},
    "pandi": {"name": "פנדי", "role": "קליטת בקשות לקוחות (intake)", "emoji": "🐼"},
}


class WhatsAppAgentConfig(BaseModel):
    agent_code: str
    name: str
    role: str
    emoji: str
    instance_id: str = ""
    token: str = ""
    whatsapp_number: str = ""
    webhook_secret: str = ""
    last_updated_at: Optional[str] = None
    # Convenience flag for the UI — true iff at least instance_id + token
    # are set, i.e. enough to reach Green API. The phone-number field is
    # informational only (so the human knows which number this is).
    is_configured: bool = False


class WhatsAppAgentConfigUpdate(BaseModel):
    instance_id: str = Field(default="", max_length=200)
    token: str = Field(default="", max_length=500)
    whatsapp_number: str = Field(
        default="",
        max_length=30,
        description="E.164 phone number (e.g. +972501234567). Informational only.",
    )
    webhook_secret: str = Field(default="", max_length=200)


class WhatsAppAgentsResponse(BaseModel):
    agents: list[WhatsAppAgentConfig]


async def _fetch_settings_dict(supabase, prefix: str) -> tuple[dict[str, str], Optional[str]]:
    """Return {field_name -> setting_value} for keys matching 'prefix.*'.

    Also returns the most recent updated_at among the matched rows, so the
    UI can show "last saved" per agent.
    """
    resp = await (
        supabase.table("system_settings")
        .select("setting_key, setting_value, updated_at")
        .like("setting_key", f"{prefix}.%")
        .execute()
    )
    rows = resp.data or []
    out: dict[str, str] = {}
    latest: Optional[str] = None
    for row in rows:
        key = row.get("setting_key", "")
        field = key.split(".", 1)[1] if "." in key else key
        out[field] = row.get("setting_value", "") or ""
        ts = row.get("updated_at")
        if ts and (latest is None or ts > latest):
            latest = ts
    return out, latest


def _build_config(agent_code: str, settings: dict[str, str], last_updated: Optional[str]) -> WhatsAppAgentConfig:
    label = AGENT_LABELS.get(agent_code, {"name": agent_code, "role": "", "emoji": "💬"})
    instance_id = settings.get("instance_id", "")
    token = settings.get("token", "")
    return WhatsAppAgentConfig(
        agent_code=agent_code,
        name=label["name"],
        role=label["role"],
        emoji=label["emoji"],
        instance_id=instance_id,
        token=token,
        whatsapp_number=settings.get("whatsapp_number", ""),
        webhook_secret=settings.get("webhook_secret", ""),
        last_updated_at=last_updated,
        is_configured=bool(instance_id and token),
    )


async def _upsert_setting(supabase, key: str, value: str) -> None:
    """Insert-or-update one row in system_settings."""
    now = datetime.utcnow().isoformat()
    # Try update first
    upd = await (
        supabase.table("system_settings")
        .update({"setting_value": value, "updated_at": now})
        .eq("setting_key", key)
        .execute()
    )
    if upd.data:
        return
    # Otherwise insert
    await (
        supabase.table("system_settings")
        .insert({"setting_key": key, "setting_value": value, "updated_at": now})
        .execute()
    )


@router.get("/config", response_model=WhatsAppAgentsResponse)
async def get_all_whatsapp_agents(
    supabase=Depends(get_supabase_client),
) -> WhatsAppAgentsResponse:
    """Return the Green-API config for all three WhatsApp agents at once."""
    out: list[WhatsAppAgentConfig] = []
    for code in SUPPORTED_AGENTS:
        try:
            settings, last_updated = await _fetch_settings_dict(supabase, code)
        except Exception as e:
            logger.warning(f"Failed to read settings for {code}: {e}")
            settings, last_updated = {}, None
        out.append(_build_config(code, settings, last_updated))
    return WhatsAppAgentsResponse(agents=out)


@router.get("/{agent_code}/config", response_model=WhatsAppAgentConfig)
async def get_one_whatsapp_agent(
    agent_code: str,
    supabase=Depends(get_supabase_client),
) -> WhatsAppAgentConfig:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")
    settings, last_updated = await _fetch_settings_dict(supabase, agent_code)
    return _build_config(agent_code, settings, last_updated)


@router.post("/{agent_code}/config", response_model=WhatsAppAgentConfig)
async def save_whatsapp_agent_config(
    agent_code: str,
    body: WhatsAppAgentConfigUpdate,
    supabase=Depends(get_supabase_client),
) -> WhatsAppAgentConfig:
    """Save the 4 fields for ONE agent. Other agents are untouched.

    Strict separation is enforced by namespacing every key with the
    agent_code prefix. There is no shared field name anywhere — a save to
    /tal/config writes only `tal.*` keys.
    """
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")

    payload = body.model_dump()
    try:
        for field in FIELD_KEYS:
            await _upsert_setting(supabase, f"{agent_code}.{field}", str(payload.get(field, "")))
    except Exception as e:
        logger.error(f"Failed to save WhatsApp config for {agent_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save configuration")

    # Return the freshly-saved state so the UI can re-render confidently.
    settings, last_updated = await _fetch_settings_dict(supabase, agent_code)
    return _build_config(agent_code, settings, last_updated)
