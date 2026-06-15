"""Parse a recruitment-agency ("השמה") email into structured job fields.

These emails (e.g. from @adamtotal.co.il) describe a position the agency is
recruiting for. They follow a loose but consistent Hebrew layout — a "קצת על
התפקיד" section, a "מה אנחנו מחפשים" requirements list with חובה/יתרון markers,
and a contact person + phone. We use Haiku (cheap, single email) to extract the
fields rather than brittle regex, so new agency formats keep working.
"""

import asyncio
import html as _html
import json
import logging
import re
from typing import Any, Optional

from pandapower.core.config import settings
from pandapower.integrations.anthropic_client import get_anthropic_client

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You extract structured job-vacancy data from Hebrew recruitment-agency "
    "emails. The agency is hiring on behalf of a client company. Return ONLY a "
    "single valid JSON object, no prose, no markdown fences."
)

_PROMPT_TEMPLATE = """המייל הבא הוא ביקוש מחברת השמה למשרה אצל לקוח. חלץ את פרטי המשרה.

נושא המייל:
{subject}

גוף המייל:
{body}

החזר JSON בלבד עם המפתחות הבאים (אם פרט חסר — החזר null):
{{
  "job_title": "כותרת התפקיד, למשל 'מהנדס/ת פיתוח חומרה בכיר/ה'",
  "job_description": "תקציר התפקיד והאחריות (מתוך 'קצת על התפקיד')",
  "job_qualifications": "דרישות התפקיד — חובה ויתרון, כטקסט מסודר",
  "job_location": "מיקום המשרה, למשל 'באר יעקב'",
  "job_security_clearance": "רמת סיווג בטחוני אם מצוינת, אחרת null",
  "contact_name": "שם איש/אשת הקשר בחברת ההשמה",
  "contact_phone": "טלפון איש הקשר (ספרות בלבד, פורמט ישראלי)",
  "external_job_ref": "מספר/קוד משרה חיצוני אם מופיע בנושא, אחרת null"
}}"""

_PHONE_RE = re.compile(r"(?:\+972[\-\s]?|0)(?:5\d|[2-49])[\-\s]?\d{3}[\-\s]?\d{4}")


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _normalize_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    return digits if len(digits) >= 9 else None


def _call_claude(subject: str, body: str) -> str:
    client = get_anthropic_client()
    prompt = _PROMPT_TEMPLATE.format(subject=subject or "", body=(body or "")[:12000])
    resp = client.messages.create(
        model=settings.PLACEMENT_PARSE_MODEL,
        max_tokens=1500,
        temperature=0,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text if resp.content else ""


def strip_html(body: str) -> str:
    """Convert an HTML email body to clean plain text."""
    if not body:
        return ""
    t = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = _html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _clean_title(raw: str) -> str:
    """Strip 'FW:' prefix and trailing job-number/code noise from a subject."""
    t = re.sub(r"^\s*(FW|Fwd|RE)\s*:\s*", "", raw or "", flags=re.I).strip()
    # Drop trailing "(76044340) - 3149 (3140)" style codes.
    t = re.sub(r"\s*\(\s*\d[\d\-]*\s*\).*$", "", t).strip()
    t = re.sub(r"\s*[-–]\s*\d[\d\-]*\s*$", "", t).strip()
    return t


_LOC_STOPWORDS = ("נשמח", "אנחנו", "אני", "קו\"ח", 'קו"ח', "מחפשים", "למשרה", "תודה")


def _clean_location(raw: str) -> Optional[str]:
    """Keep just the city: trim at the first stop-word, cap at 3 words."""
    s = re.split(r"[,•:]", raw.strip(" :•-"))[0].strip()
    words = s.split()
    out = []
    for w in words:
        if any(sw in w for sw in _LOC_STOPWORDS):
            break
        out.append(w)
        if len(out) >= 3:
            break
    loc = " ".join(out).strip()
    return loc or None


def _section(text: str, start: str, ends: list[str]) -> Optional[str]:
    """Return the block between heading `start` and the next of `ends`."""
    si = text.find(start)
    if si == -1:
        return None
    si += len(start)
    end_positions = [text.find(e, si) for e in ends]
    end_positions = [p for p in end_positions if p != -1]
    ei = min(end_positions) if end_positions else len(text)
    block = text[si:ei].strip(" \n:•-")
    return block.strip() or None


def heuristic_parse(subject: str, body: str) -> Optional[dict[str, Any]]:
    """Parse the consistent agency (adamtotal) layout without an LLM. Used as a
    fallback when Claude is unavailable (e.g. account usage cap) or fails."""
    text = strip_html(body)
    if not text:
        return None

    # Title: prefer the inner "Subject:" line of a forwarded email, else the
    # email subject. Both get the same code-stripping cleanup.
    inner_subj = None
    m = re.search(r"Subject:\s*\n?([^\n]+)", text)
    if m:
        inner_subj = m.group(1).strip()
    title = _clean_title(inner_subj or subject or "")
    if not title:
        return None

    # Contact name from the forwarded "From: <name> <email>" header.
    contact_name = None
    fm = re.search(r"From:\s*\n?([^\n<]+?)\s*<", text)
    if fm:
        contact_name = fm.group(1).strip() or None

    # Location: "מיקום <X>", else "משרה בהשמה ב<city>". A city is 1-3 words, so
    # truncate at the first stop-word/punctuation to avoid swallowing the next
    # sentence when the layout puts the city inline.
    location = None
    lm = re.search(r"מיקום\s+([^\n]+)", text)
    if not lm:
        lm = re.search(r"משרה\s+בהשמה\s+ב?([^\n]+)", text)
    if lm:
        location = _clean_location(lm.group(1))

    description = _section(text, "קצת על התפקיד", ["מה אנחנו מחפשים", "אולי יעניין"])
    qualifications = _section(text, "מה אנחנו מחפשים", ["אולי יעניין", "תודה רבה"])

    # Security clearance: explicit "סיווג ..." mention, else a "רמה N" reference.
    clearance = None
    cm = re.search(r"סיווג\s*(?:ביטחוני|בטחוני)?\s*[:\-]?\s*([^\n,.]{1,40})", text)
    if cm and cm.group(1).strip():
        clearance = cm.group(1).strip(" :•-") or None
    if not clearance:
        rm2 = re.search(r"(רמה\s*[123]\b(?:\s*\+?\s*שוס)?)", text)
        if rm2:
            clearance = rm2.group(1).strip()

    pm = _PHONE_RE.search(text)
    phone = _normalize_phone(pm.group(0)) if pm else None

    # External ref: the (NNNNNNNN) code in the subject.
    rm = re.search(r"\((\d{5,})\)", inner_subj or subject or "")
    external_ref = rm.group(1) if rm else None

    return {
        "job_title": title,
        "job_description": description,
        "job_qualifications": qualifications,
        "job_location": location,
        "job_security_clearance": clearance,
        "contact_name": contact_name,
        "contact_phone": phone,
        "external_job_ref": external_ref,
    }


async def parse_placement_email(subject: str, body: str) -> Optional[dict[str, Any]]:
    """Return structured job fields, or None if parsing fails / yields no title.

    Tries Haiku first (handles novel agency formats); on any failure — including
    the account-level Anthropic usage cap — falls back to a deterministic
    heuristic parser tuned to the consistent agency layout. Runs the synchronous
    Anthropic client in a thread so it does not block the ingest event loop.
    """
    data: Optional[dict[str, Any]] = None
    try:
        raw = await asyncio.to_thread(_call_claude, subject, body)
        data = json.loads(_strip_fences(raw))
    except Exception as e:
        logger.warning(f"Placement LLM parse unavailable ({e}); using heuristic fallback")

    if not data or not (data.get("job_title") or "").strip():
        data = heuristic_parse(subject, body)

    if not data or not (data.get("job_title") or "").strip():
        logger.warning("Placement email produced no job_title (LLM + heuristic); skipping")
        return None

    title = (data.get("job_title") or "").strip()

    # Phone fallback: if Claude missed it, grab the first Israeli number in body.
    phone = _normalize_phone(data.get("contact_phone"))
    if not phone:
        m = _PHONE_RE.search(body or "")
        phone = _normalize_phone(m.group(0)) if m else None

    return {
        "job_title": title,
        "job_description": (data.get("job_description") or "").strip() or None,
        "job_qualifications": (data.get("job_qualifications") or "").strip() or None,
        "job_location": (data.get("job_location") or "").strip() or None,
        "job_security_clearance": (data.get("job_security_clearance") or "").strip() or None,
        "contact_name": (data.get("contact_name") or "").strip() or None,
        "contact_phone": phone,
        "external_job_ref": (data.get("external_job_ref") or "").strip() or None,
    }
