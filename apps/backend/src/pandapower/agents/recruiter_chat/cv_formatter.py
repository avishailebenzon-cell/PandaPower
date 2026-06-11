"""Panda-Tech branded CV generation for Elad's client delivery.

When a client approves receiving a candidate's CV, Elad must NOT forward the raw
uploaded file (random layout, no branding). Instead we render a clean, uniform
**"Panda-Tech format"** CV from the structured data Claude already extracted
(``candidates.extracted_from_cv``), with:

  • the company logo / branding header and the candidate's **iron number**;
  • the candidate's personal contact channels **replaced** by PandaTech's own —
    so the client always reaches the candidate through us, never directly.

Rendering pipeline: build an HTML document → ConvertAPI ``html/to/pdf`` (a
Chromium engine, so RTL + Hebrew fonts render correctly with no system
libraries on Render) → upload to Supabase storage (bucket ``cvs``) under
``formatted/{candidate_id}/...``.

Because automatic extraction is never perfect, generation only **stages** the
CV (``matches.formatted_cv_status = 'generated'``). A human previews and
approves it before ``elad_flow.send_cv_file`` will deliver it to the client.

Config (system_settings, keys ``panda_cv.*`` — all optional, sane defaults):
  panda_cv.logo_url        - absolute URL of the company logo (embedded if set)
  panda_cv.company_name    - branding text (default "PandaTech")
  panda_cv.contact_email   - agency contact email shown on the CV
  panda_cv.contact_phone   - agency contact phone shown on the CV
  panda_cv.contact_website - agency website shown on the CV
"""

from __future__ import annotations

import html as _html
import logging
from datetime import datetime
from typing import Optional

# Reuse the anonymisation primitives so the branded CV and the chat dossier
# stay consistent about what is "safe" and how raw fields are flattened.
from pandapower.agents.recruiter_chat.elad_flow import (
    _FORBIDDEN_CONTACT_KEYS,
    _age_from_birthdate,
    _join,
)

logger = logging.getLogger(__name__)

STATUS_GENERATED = "generated"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

_DEFAULT_BRANDING = {
    "logo_url": "",
    "company_name": "PandaTech",
    "contact_email": "jobs@pandatech.co.il",
    "contact_phone": "",
    "contact_website": "www.pandatech.co.il",
}


# ---------------------------------------------------------------------------
# Branding config
# ---------------------------------------------------------------------------
async def _load_branding(supabase) -> dict:
    """Return Panda-Tech branding, overlaying system_settings on the defaults."""
    branding = dict(_DEFAULT_BRANDING)
    try:
        r = await supabase.table("system_settings").select(
            "setting_key, setting_value"
        ).like("setting_key", "panda_cv.%").execute()
        for row in (r.data or []):
            field = (row.get("setting_key") or "").split(".", 1)[-1]
            val = row.get("setting_value")
            if isinstance(val, str):
                val = val.strip().strip('"').strip()
            if field in branding and val and val != "null":
                branding[field] = val
    except Exception as e:
        logger.debug(f"[panda_cv] branding read failed (using defaults): {e}")
    return branding


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
def _esc(val) -> str:
    return _html.escape(str(val)) if val is not None else ""


def _render_experience(val) -> str:
    """Render work experience as styled blocks; falls back to flat lines."""
    if isinstance(val, list):
        blocks = []
        for item in val:
            if isinstance(item, dict):
                title = item.get("position") or item.get("title") or item.get("role") or ""
                company = item.get("company") or item.get("employer") or ""
                period = (
                    item.get("duration") or item.get("dates") or item.get("period")
                    or " ".join(str(x) for x in [item.get("start_date"), item.get("end_date")] if x)
                )
                desc = item.get("description") or item.get("summary") or ""
                head = " · ".join(_esc(x) for x in [title, company] if x)
                if not (head or period or desc):
                    head = _esc(" — ".join(str(v) for v in item.values() if v))
                blocks.append(
                    f'<div class="entry">'
                    f'<div class="entry-head"><span class="entry-title">{head}</span>'
                    f'<span class="entry-period">{_esc(period)}</span></div>'
                    + (f'<div class="entry-desc">{_esc(desc)}</div>' if desc else "")
                    + "</div>"
                )
            elif item:
                blocks.append(f'<div class="entry"><div class="entry-head">{_esc(item)}</div></div>')
        if blocks:
            return "".join(blocks)
    flat = _join(val)
    return f'<div class="entry"><div class="entry-desc">{_esc(flat)}</div></div>' if flat else ""


def _render_education(val) -> str:
    if isinstance(val, list):
        blocks = []
        for item in val:
            if isinstance(item, dict):
                degree = item.get("degree") or item.get("title") or ""
                inst = item.get("institution") or item.get("school") or item.get("university") or ""
                period = item.get("year") or item.get("dates") or item.get("duration") or ""
                head = " · ".join(_esc(x) for x in [degree, inst] if x)
                if not head:
                    head = _esc(" — ".join(str(v) for v in item.values() if v))
                blocks.append(
                    f'<div class="entry"><div class="entry-head">'
                    f'<span class="entry-title">{head}</span>'
                    f'<span class="entry-period">{_esc(period)}</span></div></div>'
                )
            elif item:
                blocks.append(f'<div class="entry"><div class="entry-head">{_esc(item)}</div></div>')
        if blocks:
            return "".join(blocks)
    flat = _join(val)
    return f'<div class="entry"><div class="entry-head">{_esc(flat)}</div></div>' if flat else ""


def _chips(val) -> str:
    """Render a comma/list field as inline chips."""
    raw = _join(val, sep="|")
    items = [s.strip() for s in raw.split("|") if s.strip()]
    if not items:
        return ""
    return '<div class="chips">' + "".join(f'<span class="chip">{_esc(i)}</span>' for i in items) + "</div>"


def _section(title: str, body_html: str) -> str:
    if not body_html:
        return ""
    return f'<section><h2>{_esc(title)}</h2>{body_html}</section>'


def build_cv_html(cand_row: dict, iron_number: str, branding: dict) -> str:
    """Build the full branded HTML document for the Panda-Tech format CV."""
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

    name = g("name", "name_he") or cand_row.get("name") or "מועמד"
    city = g("city", "location")
    age = _age_from_birthdate(g("birth_date"))
    yrs = g("years_of_experience") or cand_row.get("years_of_experience")
    cur_pos = g("current_position")
    cur_cmp = g("current_company")
    clearance = g("clearance_level") or cand_row.get("clearance_level")
    summary = g("summary")

    title_bits = [x for x in [cur_pos, cur_cmp] if x]
    title_line = " @ ".join(_esc(x) for x in title_bits)

    facts = []
    if city:
        facts.append(("עיר מגורים", city))
    if age:
        facts.append(("גיל", age))
    if yrs:
        facts.append(("שנות ניסיון", yrs))
    if clearance:
        facts.append(("סיווג ביטחוני", clearance))
    facts_html = "".join(
        f'<div class="fact"><span class="fact-k">{_esc(k)}</span>'
        f'<span class="fact-v">{_esc(v)}</span></div>'
        for k, v in facts
    )

    sections = []
    if summary:
        sections.append(_section("תקציר מקצועי", f'<p>{_esc(str(summary)[:1200])}</p>'))
    sections.append(_section("ניסיון תעסוקתי", _render_experience(g("experience") or cand_row.get("experiences"))))
    sections.append(_section("השכלה", _render_education(g("education") or cand_row.get("top_education"))))
    sections.append(_section("כישורים טכניים", _chips(g("technical_skills") or cand_row.get("key_skills"))))
    sections.append(_section("כישורים אישיים", _chips(g("soft_skills"))))
    sections.append(_section("שפות", _chips(g("spoken_languages"))))
    sections.append(_section("הסמכות", _chips(g("certifications"))))
    mil = _join(g("military_service"))
    if mil:
        sections.append(_section("שירות צבאי", f'<p>{_esc(mil)}</p>'))
    sections_html = "".join(s for s in sections if s)

    logo_html = (
        f'<img class="logo" src="{_esc(branding["logo_url"])}" alt="logo" />'
        if branding.get("logo_url")
        else f'<div class="logo-text">{_esc(branding["company_name"])}</div>'
    )

    contact_bits = []
    if branding.get("contact_phone"):
        contact_bits.append(f'טלפון: {_esc(branding["contact_phone"])}')
    if branding.get("contact_email"):
        contact_bits.append(f'דוא״ל: {_esc(branding["contact_email"])}')
    if branding.get("contact_website"):
        contact_bits.append(_esc(branding["contact_website"]))
    contact_line = " · ".join(contact_bits)

    iron_html = f'<div class="iron">מספר מועמד: {_esc(iron_number)}</div>' if iron_number else ""

    return f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8" />
<style>
  @import url('https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&display=swap');
  @page {{ size: A4; margin: 0; }}
  * {{ box-sizing: border-box; }}
  html, body {{ width: 100%; margin: 0; padding: 0; }}
  body {{ font-family: 'Heebo', Arial, sans-serif; color: #1f2937; direction: rtl; }}
  .page {{ width: 100%; padding: 40px 44px; overflow: hidden; }}
  header.brand {{ display: flex; align-items: center; justify-content: space-between;
    border-bottom: 3px solid #4f46e5; padding-bottom: 16px; margin-bottom: 20px; }}
  .logo {{ max-height: 56px; }}
  .logo-text {{ font-size: 26px; font-weight: 700; color: #4f46e5; letter-spacing: 0.5px; }}
  .brand-contact {{ font-size: 11px; color: #6b7280; text-align: left; }}
  .iron {{ font-size: 12px; color: #4f46e5; font-weight: 500; margin-bottom: 4px; }}
  h1 {{ font-size: 24px; margin: 4px 0 2px; color: #111827; }}
  .title-line {{ font-size: 14px; color: #4f46e5; font-weight: 500; margin-bottom: 12px; }}
  .facts {{ display: flex; flex-wrap: wrap; gap: 8px 24px; margin-bottom: 8px; }}
  .fact {{ font-size: 13px; }}
  .fact-k {{ color: #6b7280; }}
  .fact-v {{ color: #111827; font-weight: 500; margin-right: 4px; }}
  section {{ margin-top: 18px; }}
  h2 {{ font-size: 15px; color: #4f46e5; border-bottom: 1px solid #e5e7eb;
    padding-bottom: 4px; margin: 0 0 8px; }}
  .entry {{ margin-bottom: 10px; }}
  .entry-head {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .entry-title {{ font-weight: 500; color: #111827; font-size: 13.5px; }}
  .entry-period {{ font-size: 11.5px; color: #6b7280; white-space: nowrap; margin-right: 12px; }}
  .entry-desc {{ font-size: 12.5px; color: #374151; margin-top: 2px; white-space: pre-line; }}
  p {{ font-size: 13px; line-height: 1.5; margin: 0; color: #374151; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{ background: #eef2ff; color: #3730a3; font-size: 12px;
    padding: 3px 10px; border-radius: 12px; unicode-bidi: plaintext; }}
  footer {{ margin-top: 28px; border-top: 1px solid #e5e7eb; padding-top: 10px;
    font-size: 10.5px; color: #9ca3af; text-align: center; }}
</style>
</head>
<body>
  <div class="page">
    <header class="brand">
      {logo_html}
      <div class="brand-contact">{contact_line}</div>
    </header>
    {iron_html}
    <h1>{_esc(name)}</h1>
    {f'<div class="title-line">{title_line}</div>' if title_line else ''}
    <div class="facts">{facts_html}</div>
    {sections_html}
    <footer>
      קורות חיים אלה הופקו ונמסרים על ידי {_esc(branding["company_name"])}.
      לתיאום ראיון או פרטים נוספים אנא פנו אלינו ישירות.
    </footer>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Generation (HTML → PDF → storage)
# ---------------------------------------------------------------------------
async def _load_match_candidate(supabase, match_id: str) -> Optional[dict]:
    res = await supabase.table("matches").select(
        "id, iron_number, candidate_id, formatted_cv_path, formatted_cv_status, "
        "candidates(name, cv_file_id, clearance_level, years_of_experience, "
        "extracted_from_cv, top_education, experiences, key_skills)"
    ).eq("id", str(match_id)).limit(1).execute()
    return res.data[0] if res.data else None


async def generate_formatted_cv(supabase, match_id: str, *, force: bool = False) -> dict:
    """Render and store the Panda-Tech CV for a match; stage it for review.

    Returns ``{"ok": bool, "status": str, "path": str|None, "error": str|None}``.
    When ``force`` is False and an approved CV already exists, it is returned
    untouched (we never silently overwrite a human-approved document).
    """
    row = await _load_match_candidate(supabase, match_id)
    if not row:
        return {"ok": False, "status": None, "path": None, "error": "match not found"}

    if not force and row.get("formatted_cv_status") == STATUS_APPROVED and row.get("formatted_cv_path"):
        return {"ok": True, "status": STATUS_APPROVED, "path": row["formatted_cv_path"], "error": None}

    cand = row.get("candidates") or {}
    candidate_id = row.get("candidate_id")
    iron_number = row.get("iron_number") or ""

    # Render + upload via the shared, candidate-centric helper. Elad layers its
    # approval gate and matches bookkeeping (below) on top of this.
    from pandapower.agents.shared.cv_delivery import render_and_upload_cv
    rendered = await render_and_upload_cv(
        supabase,
        cand,
        iron_number or str(match_id),
        folder=candidate_id or match_id,  # test matches may lack a candidate
    )
    if not rendered.get("ok"):
        return {"ok": False, "status": None, "path": None, "error": rendered.get("error")}
    storage_path = rendered["path"]

    try:
        await supabase.table("matches").update({
            "formatted_cv_path": storage_path,
            "formatted_cv_status": STATUS_GENERATED,
            "formatted_cv_generated_at": datetime.utcnow().isoformat(),
            "formatted_cv_approved_at": None,
            "formatted_cv_approved_by": None,
            "formatted_cv_rejected_reason": None,
        }).eq("id", str(match_id)).execute()
    except Exception as e:
        logger.error(f"[panda_cv] status update failed for match {match_id}: {e}")
        return {"ok": False, "status": None, "path": storage_path, "error": f"db update failed: {e}"}

    return {"ok": True, "status": STATUS_GENERATED, "path": storage_path, "error": None}
