"""One-shot backfill: move software-development jobs mis-routed to GC over to Naama.

Root cause (fixed in carmit.py): the Claude routing prompt fed the *candidate
pool* top-domains into the decision. Because PandaTech's pool is dominated by
business/admin profiles, Claude concluded "general business role -> gc" for
clear software jobs ("מפתחי תוכנה", C++, .NET, ML), ignoring the job text.

This script does NOT re-run matching and does NOT delete anything. Per the
instruction "preserve the matches found, just move them to the correct agent":
  • jobs.assigned_agent_code  : gc -> naama   (for the listed jobs)
  • matches (matched_by_agent_code == 'gc') for those jobs:
        matched_by_agent_code  : gc -> naama
        state_updated_by_agent : gc -> naama   (only where it was 'gc')
    All scores, states, reasoning, gaps, strengths are kept untouched.
  • mani matches on these jobs are left exactly as-is.

Run from apps/backend:
    PYTHONPATH=src .venv/bin/python scripts/backfill_reroute_software_jobs_to_naama.py --dry-run
    PYTHONPATH=src .venv/bin/python scripts/backfill_reroute_software_jobs_to_naama.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

sys.path.insert(0, "src")

from pandapower.core.supabase import get_supabase_client

NEW_AGENT = "naama"
OLD_AGENT = "gc"

# Confirmed software-development jobs to re-route (verified by title + description).
JOB_IDS = [
    ("f3d1e06a-0508-476a-87f0-2a33be78b243", "מפתחי תוכנה"),
    ("067d1f13-6252-48aa-be28-3d7a86928561", "מפתח/ת תוכנה Desktop .NET WPF + AI"),
    ("c7c96401-266d-4983-84bf-640d699c7dfb", "מפתח מערכות זמן אמת ולמידת מכונה"),
    ("b64df2b8-15a3-47a8-9772-b0080daf2cb1", "מהנדסי תוכנה ++C"),
    ("f0917055-c08f-46e2-93c7-2cb67c388406", "מוביל פיתוח מודולים אוויוניים"),
    ("26d69447-e10c-49d4-a96b-e00d908a403d", "מפתח תשתיות לינוקס ואוטומציה"),
    ("ac68e2eb-484b-4b38-a2da-6ec0cb5cf3e1", "מהנדס/ת פיתוח מבוסס לינוקס"),
]


async def main(dry_run: bool) -> int:
    sb = await get_supabase_client()
    now = datetime.utcnow().isoformat()

    for job_id, title in JOB_IDS:
        # Sanity check current assignment.
        job_resp = await sb.table("jobs").select(
            "id, job_title, assigned_agent_code"
        ).eq("id", job_id).execute()
        if not job_resp.data:
            print(f"  !! job {job_id[:8]} ({title}) NOT FOUND — skipping")
            continue
        cur = job_resp.data[0].get("assigned_agent_code")

        # Count matches that will be re-owned (gc-created only).
        gc_matches = await sb.table("matches").select(
            "id", count="exact"
        ).eq("job_id", job_id).eq("matched_by_agent_code", OLD_AGENT).execute()
        n_matches = gc_matches.count or 0

        print(f"[{job_id[:8]}] {title!r}")
        print(f"    job.assigned_agent_code: {cur!r} -> {NEW_AGENT!r}")
        print(f"    gc matches to re-own:    {n_matches}")

        if dry_run:
            print("    (dry-run, no writes)\n")
            continue

        # 1) Re-route the job.
        await sb.table("jobs").update(
            {"assigned_agent_code": NEW_AGENT}
        ).eq("id", job_id).execute()

        # 2) Re-own the gc-created matches (preserve scores/states).
        await sb.table("matches").update(
            {"matched_by_agent_code": NEW_AGENT}
        ).eq("job_id", job_id).eq("matched_by_agent_code", OLD_AGENT).execute()

        # state_updated_by_agent: only flip rows where it was gc.
        await sb.table("matches").update(
            {"state_updated_by_agent": NEW_AGENT}
        ).eq("job_id", job_id).eq("state_updated_by_agent", OLD_AGENT).execute()

        # 3) Audit trail.
        try:
            await sb.table("agent_logs").insert({
                "agent_code": NEW_AGENT,
                "action": "override_assignment",
                "related_job_id": job_id,
                "status": "success",
                "reasoning": (
                    f"Backfill re-route gc->naama: '{title}' is a software-development "
                    f"role mis-sent to GC by candidate-pool-biased routing. Job moved to "
                    f"Naama; {n_matches} existing matches preserved and re-owned."
                ),
                "created_at": now,
            }).execute()
        except Exception as e:
            print(f"    (audit log skipped: {str(e)[:80]})")

        print("    ✓ done\n")

    print("Backfill complete." if not dry_run else "Dry-run complete.")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Show plan, write nothing")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.dry_run)))
