"""Re-run the (fixed) Carmit gate logic over historical carmit_rejected matches.

Why: the old Gate 6 (relevant_skills) substring check + the 0.80 quality
threshold produced ~425 erroneous rejections. The gate logic is now fixed,
so this script re-evaluates each rejected match with the corrected gates and
promotes the ones that should have passed to 'carmit_approved' (the scheduled
task carmit_advance then moves them into Tal's queue).

Important:
  * Pure gate logic — NO Claude calls. Safe under the Anthropic usage limit.
  * Gate 1 (past_rejection) is intentionally SKIPPED: every match here has a
    prior carmit_rejected in history, so re-running it would always fail and
    defeat the purpose. We are correcting bug-induced rejections.
  * Idempotent and dry-run by default.

Run from apps/backend:
    PYTHONPATH=src python3 scripts/backfill_carmit_rejections.py            # dry-run
    PYTHONPATH=src python3 scripts/backfill_carmit_rejections.py --apply    # write
"""
import argparse
import asyncio
import os
from collections import Counter
from datetime import datetime

from dotenv import load_dotenv
from supabase import acreate_client

from pandapower.workers.carmit import CarmitOrchestrator

load_dotenv()


async def evaluate_gates(o: CarmitOrchestrator, candidate: dict, job: dict, match: dict) -> dict:
    """Run gates 2-6 (skip gate 1 = past_rejection). Returns gate_results."""
    gates: dict = {}
    gates["already_declined"] = await o._check_already_declined_gate(
        match["candidate_id"], match["job_id"]
    )
    gates["conflict_of_interest"] = await o._check_conflict_of_interest_gate(candidate, job)
    gates["clearance_match"] = await o._check_clearance_gate(candidate, job)
    gates["quality_threshold"] = await o._check_quality_score_gate(match)
    gates["relevant_skills"] = await o._check_relevant_skills_gate(candidate, job, match)
    return gates


async def main(apply: bool, limit: int | None) -> None:
    sb = await acreate_client(
        os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )
    o = CarmitOrchestrator(supabase_client=sb, anthropic_client=None, pipedrive_client=None)

    # Fetch all valid carmit_rejected matches (paginated).
    rejected: list[dict] = []
    offset = 0
    while True:
        r = await sb.table("matches").select(
            "id, candidate_id, job_id, match_score, current_state"
        ).eq("is_valid", True).eq("current_state", "carmit_rejected").range(
            offset, offset + 999
        ).execute()
        rejected.extend(r.data or [])
        if len(r.data or []) < 1000:
            break
        offset += 1000

    if limit:
        rejected = rejected[:limit]

    print(f"Evaluating {len(rejected)} carmit_rejected matches "
          f"({'APPLY' if apply else 'DRY-RUN'})\n")

    promoted = 0
    still_rejected = 0
    failed_gate_counter: Counter = Counter()
    errors = 0

    for m in rejected:
        try:
            cand = (await sb.table("candidates").select("*").eq(
                "id", m["candidate_id"]).single().execute()).data or {}
            job = (await sb.table("jobs").select("*").eq(
                "id", m["job_id"]).single().execute()).data or {}
            gates = await evaluate_gates(o, cand, job, m)
            failed = [k for k, v in gates.items() if not v["passed"]]
            if not failed:
                promoted += 1
                if apply:
                    await o._update_match_state(m["id"], "carmit_approved")
                    await o._store_match_review(
                        match_id=m["id"],
                        from_state="carmit_rejected",
                        to_state="carmit_approved",
                        gate_results=gates,
                        reasoning="Backfill: re-evaluated with fixed gates — now passes",
                    )
            else:
                still_rejected += 1
                for g in failed:
                    failed_gate_counter[g] += 1
        except Exception as e:
            errors += 1
            print(f"  ! error on match {m['id']}: {e}")

    print("\n=== SUMMARY ===")
    print(f"  would-promote -> carmit_approved : {promoted}")
    print(f"  remain rejected                  : {still_rejected}")
    print(f"  errors                           : {errors}")
    print("\n  remaining rejections by gate:")
    for g, c in failed_gate_counter.most_common():
        print(f"    {g:22} {c}")
    if not apply:
        print("\n(DRY-RUN — re-run with --apply to write changes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    asyncio.run(main(args.apply, args.limit))
