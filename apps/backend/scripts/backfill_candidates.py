"""One-time backfill: create candidates from the parsed-CV backlog.

The candidate-creation worker had a bug (fixed in candidate_creation.py +
migration 010) where it re-processed the same 20 CVs forever and never advanced
through the backlog. This script drains that backlog in a single deterministic
pass: it finds every success+is_latest CV not yet linked to a candidate and runs
the real worker logic on each EXACTLY ONCE (so unparseable CVs can't loop).
"""

import asyncio
from collections import Counter

from pandapower.core.supabase import get_supabase_client
from pandapower.workers.candidate_creation import CandidateCreationWorker

CV_SELECT = (
    "id, original_filename, llm_analysis, source_email_from, "
    "source_email_received_at, candidate_email, is_latest"
)


async def main():
    sb = await get_supabase_client()
    worker = CandidateCreationWorker(sb)

    # 1. Set of cv_file_ids already linked to a candidate.
    linked = set()
    offset = 0
    while True:
        r = await sb.table("candidates").select("cv_file_id").range(offset, offset + 999).execute()
        batch = r.data or []
        linked.update(c["cv_file_id"] for c in batch if c.get("cv_file_id"))
        if len(batch) < 1000:
            break
        offset += 1000
    print(f"Already-linked CVs: {len(linked)}")

    # 2. All success+is_latest CV ids (paginated).
    all_ids = []
    offset = 0
    while True:
        r = await sb.table("cv_files").select("id").eq(
            "parse_status", "success"
        ).eq("is_latest", True).order("created_at", desc=True).range(offset, offset + 999).execute()
        batch = r.data or []
        all_ids.extend(x["id"] for x in batch)
        if len(batch) < 1000:
            break
        offset += 1000

    todo = [i for i in all_ids if i not in linked]
    print(f"success+is_latest CVs: {len(all_ids)} | backlog to process: {len(todo)}\n")

    outcomes = Counter()
    errors = []

    # 3. Process each backlog CV exactly once, in batches (fetch full row, run worker).
    BATCH = 50
    for start in range(0, len(todo), BATCH):
        chunk_ids = todo[start:start + BATCH]
        rows = await sb.table("cv_files").select(CV_SELECT).in_("id", chunk_ids).execute()
        for cv in rows.data or []:
            try:
                outcome = await worker._create_or_update_candidate_from_cv(cv)
                outcomes[outcome] += 1
            except Exception as e:
                outcomes["error"] += 1
                errors.append((cv.get("original_filename"), str(e)[:80]))
            # Stamp cursor if the column exists (no-op otherwise).
            await worker._mark_attempted(cv["id"])

        done = min(start + BATCH, len(todo))
        print(
            f"  {done}/{len(todo)} | created={outcomes['created']} "
            f"updated={outcomes['updated']} skipped={outcomes['skipped_low_confidence']} "
            f"errors={outcomes['error']}"
        )

    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    for k, v in outcomes.items():
        print(f"  {k:24} = {v}")

    final = await sb.table("candidates").select("id", count="exact").limit(1).execute()
    print(f"\n  TOTAL candidates now: {final.count}")

    if errors:
        print(f"\n  Sample errors ({min(len(errors),10)} of {len(errors)}):")
        seen = Counter(e[1] for e in errors)
        for msg, cnt in seen.most_common(10):
            print(f"    [{cnt}x] {msg}")


if __name__ == "__main__":
    asyncio.run(main())
