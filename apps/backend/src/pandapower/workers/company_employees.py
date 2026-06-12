"""Company-employee detection for the matching pipeline.

A candidate who is CURRENTLY a company employee (Pipedrive "סטטוס איש הקשר" =
"עובד חברה", synced into contacts.contact_status = "employee") must never be
forwarded to Tal — we don't approach our own staff about company jobs. But we
DO still want their matches to appear in Carmit's screens, clearly tagged, so
we can verify the matching engine is working end-to-end.

This module is the single source of truth for "is this candidate a company
employee" and for keeping the denormalized matches.is_company_employee flag in
sync. It is used in two places:

  * workers/tasks.py :: _carmit_handoff_to_tal_async — the real-time gate that
    diverts employee matches away from Tal at handoff time.
  * workers/tasks.py :: _company_employee_sync_async — the weekly Sunday-morning
    job that refreshes the flag across ALL matches (and recalls any employee
    match that already slipped into Tal's queue).

Linkage is intentionally tolerant: candidates.contact_id (added late, in
migration 021) is sparsely populated, so we ALSO match a candidate to an
employee contact by normalized phone and lower-cased email.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from pandapower.core.phone import to_international

logger = logging.getLogger(__name__)

EMPLOYEE_STATUS = "employee"


def _chunks(items: list, size: int = 150) -> Iterable[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _load_employee_identifiers(supabase) -> dict[str, set]:
    """Return the identifier sets for every current company-employee contact.

    {contact_ids, emails (lower), phones (international)}. Employees are a small
    set (company staff), so loading them all in one shot is cheap and lets us
    test candidates against them locally.
    """
    contact_ids: set[str] = set()
    emails: set[str] = set()
    phones: set[str] = set()
    try:
        resp = await (
            supabase.table("contacts")
            .select("id, email, phone")
            .eq("contact_status", EMPLOYEE_STATUS)
            .execute()
        )
        for row in resp.data or []:
            if row.get("id"):
                contact_ids.add(str(row["id"]))
            email = (row.get("email") or "").strip().lower()
            if email:
                emails.add(email)
            intl = to_international(row.get("phone"))
            if intl:
                phones.add(intl)
    except Exception as e:
        logger.warning(f"Failed to load employee identifiers: {e}")
    return {"contact_ids": contact_ids, "emails": emails, "phones": phones}


def _candidate_is_employee(candidate: dict, ids: dict[str, set]) -> bool:
    if candidate.get("contact_id") and str(candidate["contact_id"]) in ids["contact_ids"]:
        return True
    email = (candidate.get("email") or "").strip().lower()
    if email and email in ids["emails"]:
        return True
    intl = to_international(candidate.get("phone"))
    if intl and intl in ids["phones"]:
        return True
    return False


async def get_employee_candidate_ids(supabase, candidate_ids: list[str]) -> set[str]:
    """Given a (small) set of candidate ids, return the subset who are company
    employees. Used by the Carmit→Tal handoff to gate a batch in real time."""
    candidate_ids = [c for c in candidate_ids if c]
    if not candidate_ids:
        return set()
    ids = await _load_employee_identifiers(supabase)
    if not (ids["contact_ids"] or ids["emails"] or ids["phones"]):
        return set()

    result: set[str] = set()
    for chunk in _chunks(list(set(candidate_ids))):
        try:
            resp = await (
                supabase.table("candidates")
                .select("id, email, phone, contact_id")
                .in_("id", chunk)
                .execute()
            )
        except Exception as e:
            logger.warning(f"get_employee_candidate_ids: candidate fetch failed: {e}")
            continue
        for cand in resp.data or []:
            if _candidate_is_employee(cand, ids):
                result.add(str(cand["id"]))
    return result


async def sync_company_employee_flags(supabase) -> dict[str, Any]:
    """Recompute matches.is_company_employee across the whole table.

    Walks every candidate, decides employee status from the freshly-synced
    contacts table, then:
      * stamps is_company_employee on all of an employee's matches,
      * clears the flag on matches whose candidate is no longer an employee,
      * recalls any employee match sitting in 'sent_to_tal' back to
        'carmit_approved' so Tal never contacts a company employee.

    Returns stats. Safe to run repeatedly (idempotent).
    """
    ids = await _load_employee_identifiers(supabase)
    employees_loaded = len(ids["contact_ids"]) + len(ids["emails"]) + len(ids["phones"])

    # 1) Find every candidate id that is a company employee.
    employee_candidate_ids: set[str] = set()
    page_size = 1000
    offset = 0
    while True:
        try:
            resp = await (
                supabase.table("candidates")
                .select("id, email, phone, contact_id")
                .range(offset, offset + page_size - 1)
                .execute()
            )
        except Exception as e:
            logger.error(f"sync_company_employee_flags: candidate page fetch failed: {e}")
            break
        rows = resp.data or []
        for cand in rows:
            if _candidate_is_employee(cand, ids):
                employee_candidate_ids.add(str(cand["id"]))
        if len(rows) < page_size:
            break
        offset += page_size

    flagged = 0
    recalled = 0
    cleared = 0

    # 2) Flag all matches of employee candidates + recall any in Tal's queue.
    if employee_candidate_ids:
        for chunk in _chunks(list(employee_candidate_ids)):
            try:
                await (
                    supabase.table("matches")
                    .update({"is_company_employee": True})
                    .in_("candidate_id", chunk)
                    .eq("is_company_employee", False)
                    .execute()
                )
            except Exception as e:
                logger.warning(f"flagging chunk failed: {e}")
            # Recall employee matches that already reached Tal's queue back to
            # carmit_approved (they stay visible in Carmit, tagged, never sent).
            try:
                r = await (
                    supabase.table("matches")
                    .update({"current_state": "carmit_approved", "is_company_employee": True})
                    .in_("candidate_id", chunk)
                    .eq("current_state", "sent_to_tal")
                    .execute()
                )
                recalled += len(r.data or [])
            except Exception as e:
                logger.warning(f"recall chunk failed: {e}")
        # Count how many matches are now flagged (for reporting).
        try:
            c = await (
                supabase.table("matches")
                .select("id", count="exact")
                .eq("is_company_employee", True)
                .execute()
            )
            flagged = c.count or 0
        except Exception:
            flagged = 0

    # 3) Clear the flag on matches whose candidate is no longer an employee
    #    (e.g. status changed in Pipedrive). Only scan currently-flagged rows.
    try:
        flagged_resp = await (
            supabase.table("matches")
            .select("candidate_id")
            .eq("is_company_employee", True)
            .execute()
        )
        flagged_candidate_ids = {
            str(r["candidate_id"]) for r in (flagged_resp.data or []) if r.get("candidate_id")
        }
        stale = list(flagged_candidate_ids - employee_candidate_ids)
        for chunk in _chunks(stale):
            r = await (
                supabase.table("matches")
                .update({"is_company_employee": False})
                .in_("candidate_id", chunk)
                .eq("is_company_employee", True)
                .execute()
            )
            cleared += len(r.data or [])
    except Exception as e:
        logger.warning(f"clearing stale flags failed: {e}")

    result = {
        "status": "success",
        "employee_identifiers_loaded": employees_loaded,
        "employee_candidates": len(employee_candidate_ids),
        "matches_flagged_total": flagged,
        "matches_recalled_from_tal": recalled,
        "matches_flag_cleared": cleared,
    }
    logger.info(f"sync_company_employee_flags: {result}")
    return result
