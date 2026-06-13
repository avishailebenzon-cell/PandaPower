"""Candidate-form → Pipedrive note sync.

Candidates that pass Tal's screening fill in a Google Form. Each submission
appends a row to the form's responses Google Sheet. This job, run once every
couple of nights, pulls the new rows and, for each one:

  1. Finds the candidate in Pipedrive by phone (then email).
  2. If found  → adds a note with ALL the form fields onto that contact.
  3. If missing → creates the contact (name / phone / email) and then adds
     the same note.

It does NOT poll continuously — the scheduler ticks it hourly but it self-gates
to run at most once per ~2 days, during the Israeli night.

Reading the sheet
-----------------
The sheet is read as published CSV (File → Share → Publish to web → CSV). The
CSV URL is stored in system_settings under ``candidate_form.csv_url`` (or the
``CANDIDATE_FORM_CSV_URL`` env var) so it can be changed without a redeploy.
No Google credentials live in the codebase.

Cursor
------
Google Forms only ever *appends* rows, so a simple processed-row-count cursor
(``candidate_form.processed_rows``) is robust: each run processes
``rows[processed:]`` and advances the count. The last processed timestamp is
stored for visibility only.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import structlog

from pandapower.core.config import settings
from pandapower.core.phone import to_international, is_valid
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.pipedrive_client import PipedriveClient
from pandapower.workers.tasks import _get_setting, _set_setting

logger = structlog.get_logger(__name__)

# system_settings keys
CSV_URL_KEY = "candidate_form.csv_url"
PROCESSED_ROWS_KEY = "candidate_form.processed_rows"
LAST_RUN_KEY = "candidate_form.last_run_at"
LAST_TS_KEY = "candidate_form.last_timestamp"

# Run at most once every ~2 days, only during the Israeli night.
MIN_HOURS_BETWEEN_RUNS = 47
NIGHT_HOURS_ISRAEL = range(1, 6)  # 01:00–05:59 local
ISRAEL_UTC_OFFSET = 3  # IDT; good enough for a nightly window


def _israel_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=ISRAEL_UTC_OFFSET)


def _looks_like(header: str, *needles: str) -> bool:
    h = (header or "").strip().lower()
    return any(n in h for n in needles)


def _extract_contact(row: dict[str, str]) -> tuple[str, Optional[str], Optional[str]]:
    """Pull (full_name, phone, email) out of a form row by header keywords."""
    first = last = full = phone = email = ""
    for header, value in row.items():
        v = (value or "").strip()
        if not v:
            continue
        if _looks_like(header, "משפחה"):
            last = v
        elif _looks_like(header, "פרטי"):
            first = v
        elif _looks_like(header, "שם מלא", "full name", "שם ושם"):
            full = v
        elif not full and _looks_like(header, "שם", "name"):
            full = v
        elif _looks_like(header, "טלפון", "נייד", "phone", "מספר", "סלולרי"):
            phone = phone or v
        elif "@" in v or _looks_like(header, "מייל", "אימייל", "דוא", "email", "e-mail"):
            email = email or v

    name = (f"{first} {last}".strip()) or full or "מועמד ללא שם"
    return name, (phone or None), (email or None)


def _build_note(row: dict[str, str]) -> str:
    """All form columns as a Pipedrive note (HTML), one 'header: value' per line."""
    lines = ["🐼 <b>טופס מועמד — נקלט אוטומטית ממערכת PandaPower</b>", ""]
    for header, value in row.items():
        v = (value or "").strip()
        if not header:
            continue
        lines.append(f"<b>{header.strip()}:</b> {v or '—'}")
    return "<br>".join(lines)


async def _find_person_id(client: PipedriveClient, phone: Optional[str], email: Optional[str]) -> Optional[int]:
    """Search Pipedrive by phone (international) first, then email."""
    terms = []
    if phone and is_valid(phone):
        terms.append(to_international(phone))
    elif phone:
        terms.append(phone)
    if email:
        terms.append(email)
    for term in terms:
        try:
            items = await client.search_persons(term)
        except Exception as e:
            logger.warning("candidate_form_search_failed", term=term, error=str(e))
            continue
        if items:
            pid = items[0].get("id")
            if pid:
                return int(pid)
    return None


async def _fetch_rows(csv_url: str) -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
        resp = await http.get(csv_url)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


async def sync_candidate_form() -> dict[str, Any]:
    """One sync pass. Self-gates to the night / 2-day cadence."""
    sb = await get_supabase_client()

    csv_url = await _get_setting(sb, CSV_URL_KEY) or os.getenv("CANDIDATE_FORM_CSV_URL")
    if not csv_url:
        return {"status": "skipped", "reason": "candidate_form.csv_url not configured"}
    if not settings.PIPEDRIVE_API_TOKEN:
        return {"status": "skipped", "reason": "pipedrive token missing"}

    # Night / cadence guard.
    if _israel_now().hour not in NIGHT_HOURS_ISRAEL:
        return {"status": "skipped", "reason": "outside night window"}
    last_run = await _get_setting(sb, LAST_RUN_KEY)
    if last_run:
        try:
            elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last_run).replace(tzinfo=timezone.utc)
            if elapsed < timedelta(hours=MIN_HOURS_BETWEEN_RUNS):
                return {"status": "skipped", "reason": "ran recently"}
        except Exception:
            pass

    try:
        rows = await _fetch_rows(csv_url)
    except Exception as e:
        logger.error("candidate_form_fetch_failed", error=str(e))
        return {"status": "failed", "error": f"fetch CSV: {e}"}

    try:
        processed = int(await _get_setting(sb, PROCESSED_ROWS_KEY) or 0)
    except (TypeError, ValueError):
        processed = 0

    new_rows = rows[processed:]
    if not new_rows:
        await _set_setting(sb, LAST_RUN_KEY, datetime.now(timezone.utc).isoformat())
        return {"status": "completed", "new_rows": 0, "total_rows": len(rows)}

    client = PipedriveClient(api_token=settings.PIPEDRIVE_API_TOKEN)
    created = matched = noted = errors = 0
    try:
        for row in new_rows:
            try:
                name, phone, email = _extract_contact(row)
                person_id = await _find_person_id(client, phone, email)
                if person_id:
                    matched += 1
                else:
                    person = await client.create_person(name=name, email=email, phone=phone)
                    person_id = person.get("id")
                    created += 1
                if person_id:
                    await client.create_person_note(int(person_id), _build_note(row))
                    noted += 1
            except Exception as e:
                errors += 1
                logger.error("candidate_form_row_failed", name=row, error=str(e))
                # Stop on first error so the cursor doesn't skip an unprocessed row.
                break
            processed += 1
    finally:
        await client.close()

    await _set_setting(sb, PROCESSED_ROWS_KEY, str(processed))
    await _set_setting(sb, LAST_RUN_KEY, datetime.now(timezone.utc).isoformat())
    if new_rows:
        ts_col = next(iter(new_rows[0].keys()), None)
        if ts_col:
            await _set_setting(sb, LAST_TS_KEY, str(new_rows[min(processed, len(new_rows)) - 1].get(ts_col, "")))

    return {
        "status": "completed" if errors == 0 else "partial",
        "new_rows": len(new_rows),
        "matched": matched,
        "created": created,
        "noted": noted,
        "errors": errors,
        "processed_total": processed,
    }
