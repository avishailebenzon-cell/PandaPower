"""Parse a recruitment-agency ("השמה") email into structured job fields.

These emails (e.g. from @adamtotal.co.il) describe a position the agency is
recruiting for. They follow a loose but consistent Hebrew layout — a "קצת על
התפקיד" section, a "מה אנחנו מחפשים" requirements list with חובה/יתרון markers,
and a contact person + phone. We use Haiku (cheap, single email) to extract the
fields rather than brittle regex, so new agency formats keep working.
"""

import asyncio
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


async def parse_placement_email(subject: str, body: str) -> Optional[dict[str, Any]]:
    """Return structured job fields, or None if parsing fails / yields no title.

    Runs the (synchronous) Anthropic client in a thread so it does not block the
    email-ingest event loop.
    """
    try:
        raw = await asyncio.to_thread(_call_claude, subject, body)
        data = json.loads(_strip_fences(raw))
    except Exception as e:
        logger.error(f"Placement email parse failed: {e}", exc_info=True)
        return None

    title = (data.get("job_title") or "").strip()
    if not title:
        logger.warning("Placement email parsed but produced no job_title; skipping")
        return None

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
