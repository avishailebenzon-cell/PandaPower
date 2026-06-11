"""Elad's client-facing placement flow.

Elad is a *sales* agent. Unlike Tal (who screens the candidate), Elad talks to
the **client** — the company that opened the job — and presents a candidate we
already vetted, in sales language, explaining why we believe the candidate fits.

Hard rules this module enforces around the LLM:
  • The candidate's **personal contact details are never exposed** (no phone,
    no email). Everything else from the CV is fair game: name, city, age,
    education, experience, skills, languages, summary, and Carmit's assessment.
  • The candidate is tracked by an **iron number** (REF-2026-XXXX) for the whole
    conversation.
  • The original CV file is sent **only after the client's explicit approval**,
    chosen from two options (receive full CV / not now) — delivered as Green-API
    buttons with a numbered-text fallback.

Visible status, progressed automatically from the conversation
(``matches.elad_stage``):
    client_contacted → details_sent → awaiting_cv_decision → cv_sent / cv_declined

These helpers take the live ``RecruiterChatEngine`` so they can reuse its
Supabase handle, Anthropic client, phone resolution, Green-API creds and
message persistence — keeping the shared engine untouched for Tal.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, date
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)

IRON_PREFIX = "REF-2026-"
IRON_START = 1001  # first iron number → REF-2026-1001

# Stable button ids for the CV-approval prompt.
CV_YES_ID = "elad_cv_yes"
CV_NO_ID = "elad_cv_no"

# elad_stage values
STAGE_CONTACTED = "client_contacted"
STAGE_DETAILS = "details_sent"
STAGE_AWAITING = "awaiting_cv_decision"
STAGE_CV_SENT = "cv_sent"
STAGE_CV_DECLINED = "cv_declined"

_STAGE_ORDER = {
    None: 0,
    STAGE_CONTACTED: 1,
    STAGE_DETAILS: 2,
    STAGE_AWAITING: 3,
    STAGE_CV_SENT: 4,
    STAGE_CV_DECLINED: 4,
}

CLASSIFIER_MODEL = "claude-3-5-haiku-latest"


# ---------------------------------------------------------------------------
# Iron number
# ---------------------------------------------------------------------------
async def ensure_iron_number(engine, match_id) -> Optional[str]:
    """Return this match's iron number, generating a sequential one if absent.

    Best-effort and schema-defensive: returns None if the column is missing
    (pre-migration) so the flow degrades to "no iron number" rather than break.
    """
    if not match_id:
        return None
    supabase = await engine._get_supabase()
    try:
        res = await supabase.table("matches").select("iron_number").eq(
            "id", str(match_id)
        ).limit(1).execute()
        if res.data and res.data[0].get("iron_number"):
            return res.data[0]["iron_number"]
    except Exception as e:
        logger.warning(f"elad: iron_number read failed for {match_id}: {e}")
        return None

    # Compute the next sequential number from the current max.
    next_num = IRON_START
    try:
        mx = await supabase.table("matches").select("iron_number").not_.is_(
            "iron_number", "null"
        ).order("iron_number", desc=True).limit(1).execute()
        if mx.data and mx.data[0].get("iron_number"):
            tail = str(mx.data[0]["iron_number"]).rsplit("-", 1)[-1]
            if tail.isdigit():
                next_num = max(IRON_START, int(tail) + 1)
    except Exception as e:
        logger.debug(f"elad: iron_number max lookup fell back to default: {e}")

    iron = f"{IRON_PREFIX}{next_num}"
    try:
        await supabase.table("matches").update({"iron_number": iron}).eq(
            "id", str(match_id)
        ).execute()
    except Exception as e:
        logger.warning(f"elad: could not persist iron_number for {match_id}: {e}")
        return None
    return iron


# ---------------------------------------------------------------------------
# Client recipient resolution (real, non-test matches)
# ---------------------------------------------------------------------------
async def resolve_client_phone(engine, match_id) -> tuple[Optional[str], Optional[str]]:
    """Resolve the CLIENT contact's phone for a real Elad match.

    Elad's counterpart is the contact person at the company that opened the job
    — NOT the candidate. We locate them via the job's Pipedrive organisation
    (``jobs.org_id`` → ``contacts.pipedrive_org_id``), preferring the contact
    whose name matches ``jobs.contact_person_name``, else the first org contact
    that has a phone.

    Returns ``(raw_phone, contact_id)`` or ``(None, None)``. Best-effort.
    """
    supabase = await engine._get_supabase()
    try:
        m = await supabase.table("matches").select(
            "jobs(org_id, contact_person_name)"
        ).eq("id", str(match_id)).limit(1).execute()
        job = (m.data[0].get("jobs") if m.data else None) or {}
    except Exception as e:
        logger.warning(f"elad: client job lookup failed for {match_id}: {e}")
        return None, None

    org_id = job.get("org_id")
    want_name = (job.get("contact_person_name") or "").strip()
    if not org_id:
        logger.info(f"elad: match {match_id} job has no org_id — cannot resolve client phone")
        return None, None

    try:
        rows = await supabase.table("contacts").select(
            "id, full_name, phone"
        ).eq("pipedrive_org_id", org_id).execute()
    except Exception as e:
        logger.warning(f"elad: contacts lookup failed for org {org_id}: {e}")
        return None, None

    with_phone = [r for r in (rows.data or []) if (r.get("phone") or "").strip()]
    if not with_phone:
        logger.info(f"elad: no org-{org_id} contact has a phone for match {match_id}")
        return None, None

    if want_name:
        for r in with_phone:
            if (r.get("full_name") or "").strip() == want_name:
                return r["phone"], r["id"]
    return with_phone[0]["phone"], with_phone[0]["id"]


# ---------------------------------------------------------------------------
# Candidate dossier (anonymised — NO phone / email)
# ---------------------------------------------------------------------------
def _age_from_birthdate(raw) -> Optional[int]:
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y"):
        try:
            d = datetime.strptime(s[: len(fmt) + 4], fmt).date() if fmt == "%Y" else datetime.strptime(s, fmt).date()
            today = date.today()
            age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
            if 14 < age < 100:
                return age
        except Exception:
            continue
    # Bare 4-digit year fallback
    if len(s) >= 4 and s[:4].isdigit():
        try:
            age = date.today().year - int(s[:4])
            if 14 < age < 100:
                return age
        except Exception:
            pass
    return None


def _join(val, sep="\n") -> str:
    """Render a CV field that may be a string, list, or list of dicts."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, list):
        parts = []
        for item in val:
            if isinstance(item, dict):
                bits = [str(v) for v in item.values() if v]
                parts.append(" — ".join(bits))
            elif item:
                parts.append(str(item))
        return sep.join(p for p in parts if p)
    if isinstance(val, dict):
        return " — ".join(str(v) for v in val.values() if v)
    return str(val)


# Fields we must NEVER surface to the client before the CV is approved.
_FORBIDDEN_CONTACT_KEYS = (
    "phone", "alt_phone", "email", "linkedin_url", "github_url",
    "portfolio_url", "references", "name_en",
)


def build_candidate_dossier(cand_row: dict, carmit_notes: str = "", iron_number: str = "") -> str:
    """Build the full *anonymised* candidate profile Elad presents to the client.

    Includes name, city, age and all CV content (occupations, education,
    skills, languages, summary) plus Carmit's assessment. Deliberately omits all
    personal contact channels.
    """
    cand_row = cand_row or {}
    ef = {}
    efc = cand_row.get("extracted_from_cv")
    if isinstance(efc, dict):
        ef = efc.get("extracted_fields") or {}

    def g(*keys):
        for k in keys:
            if k in _FORBIDDEN_CONTACT_KEYS:
                continue
            v = ef.get(k) if k in ef else cand_row.get(k)
            if v:
                return v
        return None

    lines = []
    if iron_number:
        lines.append(f"מספר מועמד (מספר ברזל): {iron_number}")
    name = g("name", "name_he") or cand_row.get("name")
    if name:
        lines.append(f"שם: {name}")
    city = g("city", "location")
    if city:
        lines.append(f"עיר מגורים: {city}")
    age = _age_from_birthdate(g("birth_date"))
    if age:
        lines.append(f"גיל: {age}")
    yrs = g("years_of_experience") or cand_row.get("years_of_experience")
    if yrs:
        lines.append(f"שנות ניסיון: {yrs}")
    cur = g("current_position")
    cmp = g("current_company")
    if cur or cmp:
        lines.append("תפקיד נוכחי: " + " @ ".join(x for x in [str(cur or ""), str(cmp or "")] if x).strip(" @"))
    clear = g("clearance_level") or cand_row.get("clearance_level")
    if clear:
        lines.append(f"סיווג ביטחוני: {clear}")

    edu = _join(g("education") or cand_row.get("top_education"))
    if edu:
        lines.append(f"השכלה:\n{edu}")
    exp = _join(g("experience") or cand_row.get("experiences"))
    if exp:
        lines.append(f"ניסיון תעסוקתי:\n{exp[:1500]}")
    tech = _join(g("technical_skills") or cand_row.get("key_skills"), sep=", ")
    if tech:
        lines.append(f"כישורים טכניים: {tech}")
    soft = _join(g("soft_skills"), sep=", ")
    if soft:
        lines.append(f"כישורים אישיים: {soft}")
    langs = _join(g("spoken_languages"), sep=", ")
    if langs:
        lines.append(f"שפות: {langs}")
    certs = _join(g("certifications"), sep=", ")
    if certs:
        lines.append(f"הסמכות: {certs}")
    mil = _join(g("military_service"))
    if mil:
        lines.append(f"שירות צבאי: {mil}")
    summary = g("summary")
    if summary:
        lines.append(f"תקציר מקצועי: {str(summary)[:600]}")
    if carmit_notes:
        lines.append(f"הערכת כרמית (מנהלת הגיוס) להתאמה: {str(carmit_notes)[:600]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Automatic stage progression
# ---------------------------------------------------------------------------
async def _load_match_stage(engine, match_id) -> dict:
    supabase = await engine._get_supabase()
    try:
        res = await supabase.table("matches").select(
            "elad_stage, elad_cv_decision, iron_number"
        ).eq("id", str(match_id)).limit(1).execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


async def _set_stage(engine, match_id, stage: str, **extra) -> None:
    supabase = await engine._get_supabase()
    payload = {"elad_stage": stage, "state_updated_at": datetime.utcnow().isoformat()}
    payload.update(extra)
    try:
        await supabase.table("matches").update(payload).eq("id", str(match_id)).execute()
    except Exception as e:
        logger.warning(f"elad: could not set stage {stage} on {match_id}: {e}")


_CLASSIFY_SYSTEM = (
    "אתה מסווג שלב בשיחת מכירה בין סוכן הצבות (אלעד, מפנדה-טק) לבין לקוח (חברה מגייסת). "
    "בהינתן תמלול השיחה, החזר אך ורק JSON תקין במבנה: "
    '{"presented_details": bool, "client_interested": bool}. '
    "presented_details=true אם אלעד כבר הציג ללקוח את פרטי המועמד (השכלה/ניסיון/כישורים) — "
    "לא רק הזכיר שיש מועמד. "
    "client_interested=true אם הלקוח הביע עניין חיובי ברור לקדם/לראות את המועמד. "
    "אל תוסיף טקסט מעבר ל-JSON."
)


async def _classify(engine, history_messages: list) -> dict:
    """Cheap structured read of the conversation stage. Fail-safe to all-false."""
    transcript = "\n".join(
        f"{'אלעד' if m['direction'] == 'outbound' else 'לקוח'}: {(m.get('text') or '').strip()}"
        for m in history_messages
        if (m.get("text") or "").strip()
    )
    if not transcript:
        return {"presented_details": False, "client_interested": False}
    try:
        resp = engine.anthropic.messages.create(
            model=CLASSIFIER_MODEL,
            max_tokens=120,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": transcript[-6000:]}],
        )
        txt = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        start, end = txt.find("{"), txt.rfind("}")
        data = json.loads(txt[start : end + 1]) if start >= 0 else {}
        return {
            "presented_details": bool(data.get("presented_details")),
            "client_interested": bool(data.get("client_interested")),
        }
    except Exception as e:
        logger.warning(f"elad: stage classify failed: {e}")
        return {"presented_details": False, "client_interested": False}


async def advance_after_turn(engine, conversation_id: UUID, conv: dict, history: list) -> None:
    """After Elad replies, progress the visible status and, when the client is
    clearly interested, offer the CV via buttons. Never sends the CV itself —
    that requires the client's explicit button choice (handled on inbound)."""
    match_id = conv.get("match_id")
    if not match_id:
        return
    cur = await _load_match_stage(engine, match_id)
    stage = cur.get("elad_stage")
    rank = _STAGE_ORDER.get(stage, 0)

    # Once we're awaiting the CV decision (or past it), there's nothing left to
    # auto-advance — skip the classifier call entirely (saves an LLM round-trip
    # on every subsequent Elad turn).
    if rank >= _STAGE_ORDER[STAGE_AWAITING]:
        return

    # Don't mark "details_sent" off the opening alone — require that the client
    # actually engaged (at least one inbound) so an enthusiastic opener doesn't
    # jump the status before any real presentation happened.
    has_client_inbound = any(m.get("direction") == "inbound" for m in history)

    signals = await _classify(engine, history)

    # details_sent — Elad has presented the candidate's profile.
    if signals["presented_details"] and has_client_inbound and rank < _STAGE_ORDER[STAGE_DETAILS]:
        await _set_stage(engine, match_id, STAGE_DETAILS,
                         elad_details_sent_at=datetime.utcnow().isoformat())
        stage, rank = STAGE_DETAILS, _STAGE_ORDER[STAGE_DETAILS]

    # awaiting_cv_decision — client interested after we presented details → offer CV.
    if (signals["client_interested"]
            and rank == _STAGE_ORDER[STAGE_DETAILS]
            and stage == STAGE_DETAILS):
        await offer_cv(engine, conversation_id, conv, cur.get("iron_number"))


async def offer_cv(engine, conversation_id: UUID, conv: dict, iron_number: Optional[str]) -> None:
    """Send the two-option CV-approval prompt (Green-API buttons, text fallback)
    and move the match to awaiting_cv_decision."""
    match_id = conv.get("match_id")
    supabase = await engine._get_supabase()
    ref = f" (מועמד {iron_number})" if iron_number else ""
    body = (
        f"נשמח לקדם 🙌 כדי שתוכלו לבחון את המועמד{ref} לעומק, נוכל לשלוח אליכם את "
        f"קורות החיים המלאים שלו (כולל פרטים אישיים).\nאיך תעדיפו להתקדם?"
    )
    buttons = [
        {"buttonId": CV_YES_ID, "buttonText": "📄 קבלת קו\"ח מלאים"},
        {"buttonId": CV_NO_ID, "buttonText": "לא לקבל כרגע"},
    ]
    raw_phone = await engine._resolve_phone(conversation_id, supabase)
    creds = await engine._load_green_api_creds(supabase)
    sent_as_buttons = False
    if raw_phone and creds:
        from pandapower.core import phone as phone_utils
        from pandapower.integrations.green_api import GreenAPIClient
        chat_id = phone_utils.to_chat_id(raw_phone)
        if chat_id:
            client = GreenAPIClient(instance_id=creds["instance_id"], token=creds["token"])
            try:
                res = await client.send_buttons(chat_id, body, buttons)
                sent_as_buttons = bool(res.get("success"))
            finally:
                await client.close()

    if sent_as_buttons:
        await engine._save_message(conversation_id, "outbound", body, supabase, author="agent")
    else:
        # Fallback: numbered text prompt; the inbound handler accepts 1/2 too.
        fallback = body + "\n\n1️⃣ לקבלת קורות החיים המלאים\n2️⃣ לא לקבל כרגע"
        await engine._save_message(conversation_id, "outbound", fallback, supabase, author="agent")
        await engine._send_whatsapp(conversation_id, fallback, supabase)

    await _set_stage(engine, match_id, STAGE_AWAITING,
                     elad_cv_offered_at=datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# CV approval handling (inbound) + delivery
# ---------------------------------------------------------------------------
_APPROVE_TOKENS = ("קבל", "קבלת", "כן", "שלח", "מעוניין", "1", "1️⃣", "yes")
_DECLINE_TOKENS = ("לא לקבל", "לא כרגע", "לא תודה", "2", "2️⃣", "no")


def interpret_cv_decision(text: Optional[str], button_id: Optional[str]) -> Optional[str]:
    """Map an inbound reply to 'approved' / 'declined' / None (not a CV answer).

    Buttons are decisive. For *free text* we only interpret SHORT replies (a few
    words) — a long sentence is left to the LLM so we don't mis-read phrases like
    "אין סיבה לא לקבל, שלחו!" (which contains "לא לקבל") as a decline."""
    if button_id == CV_YES_ID:
        return "approved"
    if button_id == CV_NO_ID:
        return "declined"
    t = (text or "").strip().lower()
    if not t:
        return None
    # Exact numeric choices are always decisive.
    if t in ("1", "1️⃣"):
        return "approved"
    if t in ("2", "2️⃣"):
        return "declined"
    # Keyword matching only on short replies (≤ 4 words) to avoid false hits
    # inside longer sentences.
    if len(t.split()) > 4:
        return None
    # Decline wins only when the reply is explicitly negative; check it first so
    # "לא לקבל"/"לא כרגע" aren't shadowed by the "קבל" inside them.
    if t.startswith("לא") or any(tok in t for tok in _DECLINE_TOKENS):
        return "declined"
    if any(t == tok or t.startswith(tok) or tok in t for tok in _APPROVE_TOKENS):
        return "approved"
    return None


async def handle_cv_decision_if_awaiting(engine, conversation_id: UUID, conv: dict,
                                         text: Optional[str], button_id: Optional[str]) -> bool:
    """If the conversation is awaiting a CV decision, act on this inbound reply.

    Returns True if the reply was consumed as a CV decision (so the normal
    auto-reply should be suppressed), else False."""
    match_id = conv.get("match_id")
    if not match_id:
        return False
    cur = await _load_match_stage(engine, match_id)
    if cur.get("elad_stage") != STAGE_AWAITING:
        return False
    decision = interpret_cv_decision(text, button_id)
    if decision is None:
        return False  # let the normal engine reply ask again

    supabase = await engine._get_supabase()
    if decision == "declined":
        await _set_stage(engine, match_id, STAGE_CV_DECLINED, elad_cv_decision="declined")
        msg = "אין בעיה כלל 🙏 נשאיר את המועמד זמין עבורכם — אם תרצו לקבל את קורות החיים בהמשך, פשוט עדכנו אותי."
        await engine._save_message(conversation_id, "outbound", msg, supabase, author="agent")
        await engine._send_whatsapp(conversation_id, msg, supabase)
        return True

    # Approved → send the original CV file.
    ok = await send_cv_file(engine, conversation_id, conv)
    if ok:
        await _set_stage(engine, match_id, STAGE_CV_SENT,
                         elad_cv_decision="approved",
                         elad_cv_sent_at=datetime.utcnow().isoformat())
        msg = "מצוין! שלחתי לכם כעת את קורות החיים המלאים 📄 אשמח לתאם את ההמשך מולכם."
    else:
        msg = "תודה! אני מעביר את הבקשה — קורות החיים יישלחו אליכם בהקדם."
        await _set_stage(engine, match_id, STAGE_AWAITING, elad_cv_decision="approved")
    await engine._save_message(conversation_id, "outbound", msg, supabase, author="agent")
    await engine._send_whatsapp(conversation_id, msg, supabase)
    return True


async def send_cv_file(engine, conversation_id: UUID, conv: dict) -> bool:
    """Deliver the candidate's CV to the client over WhatsApp — in Panda-Tech format.

    We never forward the raw uploaded file; the client only ever receives the
    branded "Panda-Tech format" CV. Elad now **auto-sends** on the client's own
    explicit positive approval (the CV-offer buttons), with no human-in-the-loop
    gate — mirroring Pandi (see
    :func:`pandapower.agents.pandi.tool_handlers.handle_send_candidate_cv`).
    If a rendered CV doesn't exist yet, we render one on the fly and deliver it.
    """
    supabase = await engine._get_supabase()
    match_id = conv.get("match_id")
    try:
        m = await supabase.table("matches").select(
            "candidate_id, iron_number, formatted_cv_path, formatted_cv_status, candidates(name)"
        ).eq("id", str(match_id)).limit(1).execute()
        row = m.data[0] if m.data else {}
        cand = row.get("candidates") or {}
        cand_name = cand.get("name") or "candidate"
        cv_status = row.get("formatted_cv_status")
        storage_path = row.get("formatted_cv_path")
        iron = row.get("iron_number") or ""
    except Exception as e:
        logger.error(f"elad: CV lookup failed for match {match_id}: {e}")
        return False

    # Auto-render the Panda-Tech CV if one isn't staged yet. No approval gate:
    # the client already chose "receive full CV", so we deliver immediately.
    if not storage_path:
        from pandapower.agents.recruiter_chat import cv_formatter
        try:
            gen = await cv_formatter.generate_formatted_cv(supabase, match_id)
        except Exception as e:
            logger.error(f"elad: could not render formatted CV for {match_id}: {e}")
            return False
        if not gen.get("ok") or not gen.get("path"):
            logger.error(f"elad: formatted CV render failed for {match_id}: {gen.get('error')}")
            return False
        storage_path = gen["path"]

    filename = f"PandaTech_CV_{iron or cand_name}.pdf"

    from pandapower.agents.shared.cv_delivery import signed_cv_url, send_cv_file_via
    signed_url = await signed_cv_url(supabase, storage_path)
    if not signed_url:
        return False

    raw_phone = await engine._resolve_phone(conversation_id, supabase)
    creds = await engine._load_green_api_creds(supabase)
    if not (raw_phone and creds):
        return False
    from pandapower.core import phone as phone_utils
    from pandapower.integrations.green_api import GreenAPIClient
    chat_id = phone_utils.to_chat_id(raw_phone)
    if not chat_id:
        return False
    client = GreenAPIClient(instance_id=creds["instance_id"], token=creds["token"])
    try:
        ok = await send_cv_file_via(
            supabase, client, chat_id, storage_path, filename, signed_url=signed_url,
        )
    finally:
        await client.close()

    # Record the transferred file as its own chat message so the conversation
    # screen shows a "file sent" marker with a link to view the CV.
    if ok:
        try:
            await engine._save_message(
                conversation_id, "outbound", filename, supabase,
                author="agent", message_type="file", file_url=signed_url,
            )
        except Exception as e:
            logger.error(f"elad: failed to record CV file message for {match_id}: {e}")
        # Auto-approve bookkeeping: Elad sent on the client's own approval, so
        # mark the rendered CV as delivered (no separate human approval step).
        try:
            await supabase.table("matches").update({
                "formatted_cv_status": "approved",
                "formatted_cv_path": storage_path,
                "formatted_cv_approved_at": datetime.utcnow().isoformat(),
                "formatted_cv_approved_by": "elad-auto",
            }).eq("id", str(match_id)).execute()
        except Exception as e:
            logger.warning(f"elad: could not stamp auto-approved CV for {match_id}: {e}")
    return ok
