#!/usr/bin/env python3
"""
One-shot fixup: re-extract candidate_email from cv_files.llm_analysis,
applying the sender_blocklist so intermediary emails (info@jobnet.co.il,
jobs@pandatech.co.il, etc.) get replaced with the candidate's real email
from inside the CV, or NULL when there isn't a real one.

Also cleans up candidates.email by the same rule.

Run with --dry-run first to preview:
    cd apps/backend
    PYTHONPATH=./src ./.venv/bin/python3 scripts/fix_candidate_emails.py --dry-run

Then for real:
    PYTHONPATH=./src ./.venv/bin/python3 scripts/fix_candidate_emails.py

The script is idempotent — running it twice is harmless.
"""

import argparse
import asyncio
import sys
from collections import Counter

from pandapower.core.supabase import get_supabase_client
from pandapower.workers.sender_blocklist import (
    BLOCKED_DOMAINS,
    BLOCKED_EXACT,
    is_likely_candidate_email,
    is_sender_email,
)


async def fix_cv_files(dry_run: bool) -> dict:
    """Rewrite cv_files.candidate_email when current value is a sender."""
    sb = await get_supabase_client()
    stats = Counter()

    # Pull every successfully-parsed CV. We iterate Python-side so we can
    # consult llm_analysis to find the REAL email.
    rows = await sb.table("cv_files").select(
        "id, candidate_email, llm_analysis, original_filename"
    ).eq("parse_status", "success").execute()

    total = len(rows.data or [])
    print(f"Scanning {total} successfully-parsed CVs...")
    print()

    for cv in rows.data or []:
        cv_id = cv["id"]
        current = (cv.get("candidate_email") or "").strip().lower() or None

        # What's the REAL email from the CV content?
        llm = cv.get("llm_analysis") or {}
        extracted = (llm.get("extracted_fields") or {})
        from_cv = (extracted.get("email") or "").strip().lower() or None

        # Decide the corrected value:
        if from_cv and is_likely_candidate_email(from_cv):
            new_value = from_cv
        elif current and is_likely_candidate_email(current):
            # Current value is already a real candidate email — keep it
            new_value = current
        else:
            # Neither source has a real email — null it out so dedup doesn't
            # glue people together by their job-board mailbox.
            new_value = None

        # No change needed?
        if (current or None) == (new_value or None):
            stats["unchanged"] += 1
            continue

        action = "WOULD UPDATE" if dry_run else "UPDATING"
        print(
            f"  {action:13} cv {cv_id[:8]} | {cv.get('original_filename','')[:40]!r:40}"
            f"\n               {current!r}  →  {new_value!r}"
        )

        if not dry_run:
            await sb.table("cv_files").update({
                "candidate_email": new_value,
            }).eq("id", cv_id).execute()

        if new_value is None:
            stats["nullified"] += 1
        elif current is None:
            stats["filled"] += 1
        else:
            stats["replaced"] += 1

    return dict(stats)


async def fix_candidates(dry_run: bool) -> dict:
    """Null out candidates.email when it's actually a sender/intermediary."""
    sb = await get_supabase_client()
    stats = Counter()

    rows = await sb.table("candidates").select(
        "id, email, name, extracted_from_cv"
    ).is_("deleted_at", "null").execute()

    total = len(rows.data or [])
    print()
    print(f"Scanning {total} candidates...")
    print()

    for c in rows.data or []:
        current = (c.get("email") or "").strip().lower() or None
        if not current:
            stats["already_null"] += 1
            continue
        if is_likely_candidate_email(current):
            stats["ok"] += 1
            continue

        # Email is a sender. Try to find a real one inside the saved analysis.
        extracted = ((c.get("extracted_from_cv") or {}).get("extracted_fields") or {})
        from_cv = (extracted.get("email") or "").strip().lower() or None
        if from_cv and is_likely_candidate_email(from_cv):
            new_value = from_cv
        else:
            new_value = None  # null out — we don't have a real one

        action = "WOULD UPDATE" if dry_run else "UPDATING"
        print(
            f"  {action:13} candidate {c['id'][:8]} | {c.get('name','')[:30]!r:30}"
            f"\n               {current!r}  →  {new_value!r}"
        )

        if not dry_run:
            await sb.table("candidates").update({"email": new_value}).eq(
                "id", c["id"]
            ).execute()

        if new_value is None:
            stats["nullified"] += 1
        else:
            stats["replaced"] += 1

    return dict(stats)


async def main(dry_run: bool):
    print("=" * 70)
    print("Candidate-email cleanup")
    print(f"Mode: {'DRY RUN (no writes)' if dry_run else 'LIVE (writes enabled)'}")
    print(f"Blocked domains: {len(BLOCKED_DOMAINS)}  |  Blocked exact: {len(BLOCKED_EXACT)}")
    print("=" * 70)

    cv_stats = await fix_cv_files(dry_run)
    cand_stats = await fix_candidates(dry_run)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("cv_files changes:")
    for k, v in sorted(cv_stats.items()):
        print(f"  {k:15} {v:>5}")
    print()
    print("candidates changes:")
    for k, v in sorted(cand_stats.items()):
        print(f"  {k:15} {v:>5}")
    if dry_run:
        print()
        print("(dry-run — nothing was written. Re-run without --dry-run to apply.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to the DB")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
