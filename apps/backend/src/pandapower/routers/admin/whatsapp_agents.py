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

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.integrations.green_api import get_green_api_client

# Bundled agent profile photos (square JPEGs) pushed to WhatsApp via Green API.
# Kept in the backend package so the sync works regardless of the frontend deploy.
AVATARS_DIR = Path(__file__).resolve().parents[2] / "assets" / "avatars"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/whatsapp-agents", tags=["admin", "whatsapp"])


# The fixed set of agents that have a WhatsApp presence. Adding a new one
# here is the single source of truth — the UI iterates over these.
SUPPORTED_AGENTS = ("tal", "elad", "pandi", "pandius")
AgentCode = Literal["tal", "elad", "pandi", "pandius"]

# The four fields per agent. Keys are namespaced "{agent}.{field}" in
# system_settings (matching what integrations/green_api.py reads).
FIELD_KEYS = ("instance_id", "token", "whatsapp_number", "webhook_secret")


AGENT_LABELS = {
    "tal": {"name": "טל", "role": "סוכנת ראשונית (שיחה עם מועמד)", "emoji": "👩‍💼"},
    "elad": {"name": "אלעד", "role": "הצבות (שיחה עם לקוח)", "emoji": "🤝"},
    "pandi": {"name": "ליבי", "role": "קליטת בקשות לקוחות (intake)", "emoji": "🐼"},
    "pandius": {"name": "פנדיוס", "role": "קליטת פניות מועמדים (intake)", "emoji": "🐼"},
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
    # Full public URL the admin needs to paste into the Green API console
    # under "Webhook URL" for this specific agent. Built from the incoming
    # request so it works in any environment (local / Render / preview).
    webhook_url: str = ""
    # The token shape the admin should append to the URL so we can verify
    # incoming Green-API calls. Reflects whatever they typed in the
    # `webhook_secret` field above.
    webhook_url_with_token: str = ""


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


def _public_base_url(request: Optional[Request]) -> str:
    """Compute the externally-reachable base URL of this backend.

    Render terminates TLS at the edge, so the inbound request sometimes
    reports http even though the public URL is https. Trust the
    X-Forwarded-Proto/Host headers first, then fall back to request.url.
    """
    if request is None:
        return ""
    forwarded_proto = (
        request.headers.get("x-forwarded-proto")
        or request.headers.get("X-Forwarded-Proto")
        or request.url.scheme
        or "https"
    )
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("X-Forwarded-Host")
        or request.url.netloc
    )
    return f"{forwarded_proto}://{host}".rstrip("/")


def _is_real_value(value: str) -> bool:
    """True iff a setting holds a real value, not an empty/placeholder string.

    Migrations seed pandius.* with placeholders like 'PASTE_INSTANCE_ID' or
    '+9725XXXXXXXX'. Those are non-empty but must NOT count as configured, or
    the UI shows a bot as 🟢 מוגדר before the admin entered any credentials.
    """
    v = (value or "").strip()
    if not v:
        return False
    upper = v.upper()
    if "PASTE" in upper or "XXXX" in upper:
        return False
    if upper in {"TODO", "CHANGEME", "CHANGE_ME", "YOUR_TOKEN", "YOUR_INSTANCE_ID"}:
        return False
    return True


def _build_config(
    agent_code: str,
    settings: dict[str, str],
    last_updated: Optional[str],
    request: Optional[Request] = None,
) -> WhatsAppAgentConfig:
    label = AGENT_LABELS.get(agent_code, {"name": agent_code, "role": "", "emoji": "💬"})
    instance_id = settings.get("instance_id", "")
    token = settings.get("token", "")
    webhook_secret = settings.get("webhook_secret", "")

    base_url = _public_base_url(request)
    webhook_url = f"{base_url}/webhooks/whatsapp/{agent_code}" if base_url else ""
    webhook_url_with_token = (
        f"{webhook_url}?token={webhook_secret}" if (webhook_url and webhook_secret) else webhook_url
    )

    return WhatsAppAgentConfig(
        agent_code=agent_code,
        name=label["name"],
        role=label["role"],
        emoji=label["emoji"],
        instance_id=instance_id,
        token=token,
        whatsapp_number=settings.get("whatsapp_number", ""),
        webhook_secret=webhook_secret,
        last_updated_at=last_updated,
        is_configured=_is_real_value(instance_id) and _is_real_value(token),
        webhook_url=webhook_url,
        webhook_url_with_token=webhook_url_with_token,
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
    request: Request,
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
        out.append(_build_config(code, settings, last_updated, request))
    return WhatsAppAgentsResponse(agents=out)


@router.get("/{agent_code}/config", response_model=WhatsAppAgentConfig)
async def get_one_whatsapp_agent(
    agent_code: str,
    request: Request,
    supabase=Depends(get_supabase_client),
) -> WhatsAppAgentConfig:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")
    settings, last_updated = await _fetch_settings_dict(supabase, agent_code)
    return _build_config(agent_code, settings, last_updated, request)


@router.post("/{agent_code}/config", response_model=WhatsAppAgentConfig)
async def save_whatsapp_agent_config(
    agent_code: str,
    body: WhatsAppAgentConfigUpdate,
    request: Request,
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
    return _build_config(agent_code, settings, last_updated, request)


# ============================================================================
#  PROFILE PICTURES — push the bundled agent photo to the WhatsApp account
# ----------------------------------------------------------------------------
#  Sets each agent's WhatsApp profile picture to its real avatar photo, so the
#  bot presents a believable human face to candidates/clients. Idempotent —
#  safe to re-run. Requires the agent's Green-API credentials to be configured.
# ============================================================================


class ProfilePictureResult(BaseModel):
    agent_code: str
    success: bool
    detail: str
    url_avatar: Optional[str] = None


async def _sync_one_profile_picture(agent_code: str) -> ProfilePictureResult:
    """Push the bundled photo for one agent to its WhatsApp profile."""
    photo = AVATARS_DIR / f"{agent_code}.jpg"
    if not photo.is_file():
        return ProfilePictureResult(
            agent_code=agent_code, success=False, detail="missing bundled photo"
        )

    client = await get_green_api_client(agent_code)  # type: ignore[arg-type]
    if client is None:
        return ProfilePictureResult(
            agent_code=agent_code, success=False, detail="Green API not configured"
        )

    try:
        result = await client.set_profile_picture(photo.read_bytes(), f"{agent_code}.jpg")
    finally:
        await client.close()

    if result.get("success"):
        return ProfilePictureResult(
            agent_code=agent_code, success=True, detail="updated",
            url_avatar=result.get("urlAvatar"),
        )
    return ProfilePictureResult(
        agent_code=agent_code, success=False, detail=result.get("error", "failed")
    )


class CurrentAvatar(BaseModel):
    agent_code: str
    configured: bool
    url_avatar: Optional[str] = None
    detail: str


@router.get("/{agent_code}/profile-picture", response_model=CurrentAvatar)
async def get_agent_profile_picture(agent_code: str) -> CurrentAvatar:
    """Fetch the agent's CURRENT WhatsApp profile picture URL, live from Green
    API — so the admin can see what the account actually shows, bypassing any
    WhatsApp client-side cache."""
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")

    client = await get_green_api_client(agent_code)  # type: ignore[arg-type]
    if client is None:
        return CurrentAvatar(agent_code=agent_code, configured=False, detail="Green API not configured")

    try:
        result = await client.get_my_avatar()
    finally:
        await client.close()

    if result.get("success"):
        url = result.get("url_avatar")
        return CurrentAvatar(
            agent_code=agent_code, configured=True, url_avatar=url,
            detail="has avatar" if url else "no avatar set",
        )
    return CurrentAvatar(
        agent_code=agent_code, configured=True, detail=result.get("error", "failed")
    )


@router.post("/{agent_code}/profile-picture/sync", response_model=ProfilePictureResult)
async def sync_agent_profile_picture(agent_code: str) -> ProfilePictureResult:
    """Set ONE agent's WhatsApp profile picture to its bundled avatar photo."""
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")
    return await _sync_one_profile_picture(agent_code)


@router.post("/profile-pictures/sync-all", response_model=list[ProfilePictureResult])
async def sync_all_profile_pictures() -> list[ProfilePictureResult]:
    """Set every configured WhatsApp agent's profile picture in one shot."""
    results = []
    for agent_code in SUPPORTED_AGENTS:
        results.append(await _sync_one_profile_picture(agent_code))
    return results


# ============================================================================
#  Per-bot CONVERSATIONS + DASHBOARD + BEHAVIOR + PLAYGROUND
# ----------------------------------------------------------------------------
#  Everything below is scoped by `{agent_code}/` and uses the bot's own data:
#    • conversations & messages → pandi_conversations / pandi_messages tables,
#      filtered by bot_code (column added once webhook handlers populate it).
#      Until real per-bot message ingestion lands, Tal/Elad surfaces return
#      empty data — this is honest, not a bug.
#    • behavior (system-prompt addendum + predefined Q&A) → system_settings
#      using bot-namespaced keys, so the 3 bots NEVER share rules.
#    • playground → runs the bot's full prompt through Claude and returns
#      the reply, without ever touching WhatsApp.
# ============================================================================


class ConversationListItem(BaseModel):
    id: str
    started_at: Optional[str] = None
    last_message_at: Optional[str] = None
    status: str = "active"
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    message_count: int = 0


class ConversationsResponse(BaseModel):
    bot_code: str
    total: int
    conversations: list[ConversationListItem]


class MessageItem(BaseModel):
    id: str
    direction: str          # "inbound" | "outbound"
    message_type: str = "text"
    text: Optional[str] = None
    created_at: Optional[str] = None
    llm_invoked: bool = False


class MessagesResponse(BaseModel):
    bot_code: str
    conversation_id: str
    messages: list[MessageItem]


class DashboardResponse(BaseModel):
    bot_code: str
    total_conversations: int = 0
    active_conversations: int = 0
    messages_today: int = 0
    messages_this_week: int = 0
    inbound_this_week: int = 0
    outbound_this_week: int = 0
    avg_response_minutes: Optional[float] = None
    is_configured: bool = False


class QAPair(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1, max_length=2000)


class BehaviorConfig(BaseModel):
    bot_code: str
    name: str
    role: str
    system_prompt_addendum: str = ""
    qa_pairs: list[QAPair] = []


class BehaviorUpdate(BaseModel):
    system_prompt_addendum: str = Field(default="", max_length=4000)
    qa_pairs: list[QAPair] = []


class PlaygroundRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    include_qa: bool = True


class PlaygroundResponse(BaseModel):
    bot_code: str
    user_message: str
    bot_reply: str
    duration_ms: int
    tokens_used: int
    matched_qa: Optional[str] = None       # if a Q&A pair was triggered
    used_system_prompt: str                # what we actually sent to Claude


# --- helper: does the pandi_messages table exist? -----------------------------
async def _has_messages_table(supabase) -> bool:
    """We don't always have pandi_messages in production — be defensive."""
    try:
        await supabase.table("pandi_messages").select("id").limit(1).execute()
        return True
    except Exception:
        return False


class _EmptyResp:
    """Sentinel returned when a query can't run (schema mismatch / table miss)."""
    data: list = []


async def _filtered_conversations_query(supabase, bot_code: str):
    """A query that respects per-bot scoping when the column exists.

    The production pandi_conversations table has fewer columns than the
    migration defines (no bot_code, sometimes no started_at). We try the
    most-specific query first and fall back progressively:
       1) filtered by bot_code + ordered by started_at
       2) filtered by bot_code only
       3) for the legacy "pandi" bot: unfiltered (legacy rows)
       4) empty response for tal/elad if filters fail
    Each attempt is wrapped in try/except so a schema gap can't 500 us.
    """
    # Step 1 & 2: try with bot_code filter
    for use_order in (True, False):
        try:
            q = supabase.table("pandi_conversations").select("*").eq("bot_code", bot_code).limit(100)
            if use_order:
                q = q.order("started_at", desc=True)
            return await q.execute()
        except Exception:
            continue

    # Step 3: for legacy `pandi` data, drop the filter
    if bot_code == "pandi":
        for use_order in (True, False):
            try:
                q = supabase.table("pandi_conversations").select("*").limit(100)
                if use_order:
                    q = q.order("started_at", desc=True)
                return await q.execute()
            except Exception:
                continue

    # Step 4: give up and return an empty response. Tal/Elad land here until
    # per-bot ingestion is wired.
    return _EmptyResp()


@router.get("/{agent_code}/conversations", response_model=ConversationsResponse)
async def list_conversations(
    agent_code: str,
    supabase=Depends(get_supabase_client),
) -> ConversationsResponse:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")

    convs_resp = await _filtered_conversations_query(supabase, agent_code)
    rows = convs_resp.data or []

    has_msg_table = await _has_messages_table(supabase)

    out: list[ConversationListItem] = []
    for r in rows:
        conv_id = str(r.get("id", ""))
        message_count = 0
        if has_msg_table:
            try:
                cnt = await (
                    supabase.table("pandi_messages")
                    .select("id", count="exact")
                    .eq("conversation_id", conv_id)
                    .execute()
                )
                message_count = cnt.count or 0
            except Exception:
                pass
        out.append(
            ConversationListItem(
                id=conv_id,
                started_at=r.get("started_at"),
                last_message_at=r.get("last_message_at"),
                status=r.get("status") or "active",
                contact_name=r.get("contact_name"),
                contact_phone=r.get("contact_phone"),
                message_count=message_count,
            )
        )
    return ConversationsResponse(bot_code=agent_code, total=len(out), conversations=out)


@router.get(
    "/{agent_code}/conversations/{conversation_id}/messages",
    response_model=MessagesResponse,
)
async def get_conversation_messages(
    agent_code: str,
    conversation_id: str,
    supabase=Depends(get_supabase_client),
) -> MessagesResponse:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")
    if not await _has_messages_table(supabase):
        return MessagesResponse(bot_code=agent_code, conversation_id=conversation_id, messages=[])
    resp = await (
        supabase.table("pandi_messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )
    msgs = [
        MessageItem(
            id=str(m.get("id", "")),
            direction=m.get("direction") or "inbound",
            message_type=m.get("message_type") or "text",
            text=m.get("text"),
            created_at=m.get("created_at"),
            llm_invoked=bool(m.get("llm_invoked")),
        )
        for m in (resp.data or [])
    ]
    return MessagesResponse(bot_code=agent_code, conversation_id=conversation_id, messages=msgs)


@router.get("/{agent_code}/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    agent_code: str,
    supabase=Depends(get_supabase_client),
) -> DashboardResponse:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")

    convs_resp = await _filtered_conversations_query(supabase, agent_code)
    conv_rows = convs_resp.data or []
    total = len(conv_rows)
    active = sum(1 for c in conv_rows if (c.get("status") or "active") == "active")

    settings_dict, _ = await _fetch_settings_dict(supabase, agent_code)
    is_configured = _is_real_value(settings_dict.get("instance_id", "")) and _is_real_value(
        settings_dict.get("token", "")
    )

    out = DashboardResponse(
        bot_code=agent_code,
        total_conversations=total,
        active_conversations=active,
        is_configured=is_configured,
    )

    if await _has_messages_table(supabase):
        try:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            week_start = (now - timedelta(days=7)).isoformat()

            # Pull this week's messages once and bucket locally — fewer round trips.
            week_resp = await (
                supabase.table("pandi_messages")
                .select("direction, created_at")
                .gte("created_at", week_start)
                .execute()
            )
            week_rows = week_resp.data or []
            out.messages_this_week = len(week_rows)
            out.messages_today = sum(1 for m in week_rows if (m.get("created_at") or "") >= today_start)
            out.inbound_this_week = sum(1 for m in week_rows if m.get("direction") == "inbound")
            out.outbound_this_week = sum(1 for m in week_rows if m.get("direction") == "outbound")
        except Exception as e:
            logger.warning(f"Dashboard message stats failed for {agent_code}: {e}")

    return out


# ---------------- BEHAVIOR (Q&A + prompt addendum) --------------------------

def _qa_key(agent_code: str) -> str:
    return f"{agent_code}.qa_pairs"


def _prompt_addendum_key(agent_code: str) -> str:
    return f"{agent_code}.system_prompt_addendum"


@router.get("/{agent_code}/behavior", response_model=BehaviorConfig)
async def get_behavior(
    agent_code: str,
    supabase=Depends(get_supabase_client),
) -> BehaviorConfig:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")
    label = AGENT_LABELS.get(agent_code, {"name": agent_code, "role": ""})

    # Read both rows in one query for efficiency
    keys = [_qa_key(agent_code), _prompt_addendum_key(agent_code)]
    resp = await (
        supabase.table("system_settings")
        .select("setting_key, setting_value")
        .in_("setting_key", keys)
        .execute()
    )
    rows = {r["setting_key"]: r.get("setting_value") or "" for r in (resp.data or [])}

    qa_raw = rows.get(_qa_key(agent_code), "")
    qa_pairs: list[QAPair] = []
    if qa_raw:
        try:
            parsed = json.loads(qa_raw)
            if isinstance(parsed, list):
                qa_pairs = [QAPair(**item) for item in parsed if isinstance(item, dict)]
        except Exception:
            logger.warning(f"Could not parse stored Q&A for {agent_code}; treating as empty.")

    return BehaviorConfig(
        bot_code=agent_code,
        name=label["name"],
        role=label.get("role", ""),
        system_prompt_addendum=rows.get(_prompt_addendum_key(agent_code), ""),
        qa_pairs=qa_pairs,
    )


@router.post("/{agent_code}/behavior", response_model=BehaviorConfig)
async def save_behavior(
    agent_code: str,
    body: BehaviorUpdate,
    supabase=Depends(get_supabase_client),
) -> BehaviorConfig:
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")
    qa_json = json.dumps([qa.model_dump() for qa in body.qa_pairs], ensure_ascii=False)
    await _upsert_setting(supabase, _prompt_addendum_key(agent_code), body.system_prompt_addendum)
    await _upsert_setting(supabase, _qa_key(agent_code), qa_json)
    return await get_behavior(agent_code=agent_code, supabase=supabase)


# ---------------- PLAYGROUND -------------------------------------------------

# Default-empty per-bot personas. Admins customise via behavior tab.
_DEFAULT_PERSONA = {
    "tal": "את טל, סוכנת גיוס AI (נקבה) שמשוחחת עם מועמדים בעברית בעזרת WhatsApp. דברי בלשון נקבה, ידידותית ומקצועית, התמקדי באיסוף מידע חשוב על הניסיון והציפיות של המועמד.",
    "elad": "אתה אלעד, סוכן הצבות AI שמשוחח עם לקוחות בעברית. דבר באופן עניני, ברור ואסרטיבי, מתמקד באיתור צרכי הלקוח עבור איוש משרה.",
    "pandi": "את ליבי, סוכנת קליטה AI של פנדה-טק. תפקידך לקלוט בקשות מלקוחות חדשים בעברית דרך WhatsApp ולעזור להם למצוא מועמד מתאים.",
}


def _try_match_qa(user_text: str, qa_pairs: list[QAPair]) -> Optional[QAPair]:
    """Very-light fuzzy match: substring on the question, case-insensitive."""
    t = (user_text or "").strip().lower()
    if not t:
        return None
    for qa in qa_pairs:
        q = (qa.question or "").strip().lower()
        if not q:
            continue
        # Match if the user text contains the question text, or vice versa
        if q in t or t in q:
            return qa
    return None


@router.post("/{agent_code}/playground", response_model=PlaygroundResponse)
async def run_playground(
    agent_code: str,
    body: PlaygroundRequest,
    supabase=Depends(get_supabase_client),
) -> PlaygroundResponse:
    """Send a fake user message to the bot — Claude runs with the bot's
    full configured persona + addendum + Q&A. No WhatsApp involved."""
    if agent_code not in SUPPORTED_AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_code}")

    behavior = await get_behavior(agent_code=agent_code, supabase=supabase)

    # 1. Fast-path: predefined Q&A
    matched: Optional[QAPair] = _try_match_qa(body.message, behavior.qa_pairs) if body.include_qa else None
    if matched:
        return PlaygroundResponse(
            bot_code=agent_code,
            user_message=body.message,
            bot_reply=matched.answer,
            duration_ms=0,
            tokens_used=0,
            matched_qa=matched.question,
            used_system_prompt="(fast-path: predefined Q&A)",
        )

    # 2. Otherwise call Claude with persona + addendum
    persona = _DEFAULT_PERSONA.get(agent_code, "")
    sys_prompt_parts = [persona]
    if behavior.system_prompt_addendum.strip():
        sys_prompt_parts.append("\nתוספות מינהליות:\n" + behavior.system_prompt_addendum.strip())
    if behavior.qa_pairs:
        # Surface Q&A as reference (don't force-quote)
        ref = "\n".join(f"- שאלה: {q.question}\n  תשובה: {q.answer}" for q in behavior.qa_pairs[:10])
        sys_prompt_parts.append("\nשאלות־ותשובות לדוגמה:\n" + ref)
    system_prompt = "\n".join(p for p in sys_prompt_parts if p).strip()

    prompt = f"{system_prompt}\n\nהודעת המשתמש:\n{body.message}\n\nכתוב את התשובה שלך עכשיו (תשובה אחת בלבד, בעברית, קצרה ועניינית)."

    claude = AnthropicClient(api_key=settings.ANTHROPIC_API_KEY)
    start = datetime.utcnow()
    try:
        resp = await claude.match_score_with_json(
            prompt=prompt + "\n\nהחזר JSON בלבד: {\"reply\":\"<התשובה שלך>\"}",
            model="claude-sonnet-4-5",
        )
        reply = (resp.get("parsed") or {}).get("reply", "").strip() or "(הסוכן לא החזיר תשובה)"
        tokens = int(resp.get("tokens_used") or 0)
    except Exception as e:
        logger.error(f"Playground call to Claude failed for {agent_code}: {e}")
        raise HTTPException(status_code=500, detail=f"Bot inference failed: {e}")

    duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
    return PlaygroundResponse(
        bot_code=agent_code,
        user_message=body.message,
        bot_reply=reply,
        duration_ms=duration_ms,
        tokens_used=tokens,
        matched_qa=None,
        used_system_prompt=system_prompt,
    )
