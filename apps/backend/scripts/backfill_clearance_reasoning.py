"""Re-score existing matches whose reasoning was written under the OLD
(inverted) security-clearance logic.

Background
----------
The system used to rank Hebrew clearances backwards — it treated רמה 3 as the
highest and רמה 1 as the lowest, when in reality **רמה 1 is the highest**
clearance and רמה 3 the lowest ("+ שוס" sits above the plain level). That bug
was fixed in:
  • routers/admin/recruitment_departments.py  (_CLEARANCE_RANK / _clearance_rank)
  • workers/carmit.py                          (clearance gate)
  • workers/agent_matching.py                  (_clearance_level + LLM prompt)
  • workers/candidate_matching.py              (SecurityLevel enum)

The computed clearance BADGE (match/partial/mismatch) is derived on the fly by
the API, so it self-corrects on the next page load — nothing to backfill there.

What IS baked into the DB and still wrong is the LLM-generated free text:
  • matches.match_reasoning
  • agent_logs.output_payload.strengths / gaps
which may contain phrases like "סיווג רמה 2 (גבוה מהנדרש)". This script
re-runs the SAME Claude scoring call (now using the corrected prompt that
explains רמה 1 is highest) and writes the fresh text back.

Scope / cost control
--------------------
By default we only touch matches where clearance is actually relevant — i.e.
the candidate OR the job has a non-empty, non-"ללא" clearance value. Use
--all to re-score every valid match regardless (more expensive).

Safety
------
We update only the textual explanation (match_reasoning) and the find_match log
(strengths/gaps). We do NOT overwrite match_score / current_state / is_valid,
so the pipeline state machine is never disturbed by a re-score. Use
--update-score to also refresh match_score (state is still left untouched).

Run from apps/backend:

    PYTHONPATH=src .venv/bin/python scripts/backfill_clearance_reasoning.py --dry-run
    PYTHONPATH=src .venv/bin/python scripts/backfill_clearance_reasoning.py --limit 10
    PYTHONPATH=src .venv/bin/python scripts/backfill_clearance_reasoning.py --agent naama
    PYTHONPATH=src .venv/bin/python scripts/backfill_clearance_reasoning.py --all --update-score
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Any

# Allow running as `python scripts/backfill_clearance_reasoning.py`
sys.path.insert(0, "src")

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.workers.agent_matching import AgentMatchingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("backfill_clearance_reasoning")


def _has_real_clearance(value: Any) -> bool:
    """True if the value names an actual clearance level (not empty / 'ללא')."""
    if not value:
        return False
    s = str(value).strip().lower()
    if not s:
        return False
    if s.startswith("ללא") or s.startswith("none") or s.startswith("no "):
        return False
    return True


def _clearance_relevant(candidate: dict, job: dict) -> bool:
    """A match is clearance-relevant if either side carries a real clearance."""
    return _has_real_clearance(candidate.get("clearance_level")) or _has_real_clearance(
        job.get("job_security_clearance")
    )


async def backfill_one(
    matcher: AgentMatchingWorker,
    supabase,
    match: dict,
    *,
    update_score: bool,
) -> dict:
    """Re-score and persist a single match's reasoning. Returns status dict."""
    match_id = match["id"]
    candidate_id = match.get("candidate_id")
    job_id = match.get("job_id")
    agent_code = match.get("matched_by_agent_code")

    if not candidate_id or not job_id or not agent_code:
        return {"status": "skip", "reason": "missing candidate/job/agent on match"}

    try:
        cand_resp = await supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()
        candidate = cand_resp.data
    except Exception as e:
        return {"status": "error", "reason": f"candidate fetch failed: {e}"}

    try:
        job_resp = await supabase.table("jobs").select("*").eq("id", job_id).single().execute()
        job = job_resp.data
    except Exception as e:
        return {"status": "error", "reason": f"job fetch failed: {e}"}

    # Skip rows where clearance plays no role — unless --all was requested
    # (the caller already filtered, but re-check using the full rows).
    relevant = _clearance_relevant(candidate, job)

    agent_config = matcher._get_agent_config(agent_code)
    if not agent_config:
        return {"status": "skip", "reason": f"no agent_config for {agent_code!r}"}

    try:
        result = await matcher._score_candidate_job_pair(candidate, job, agent_code, agent_config)
    except Exception as e:
        return {"status": "error", "reason": f"Claude scoring failed: {e}"}

    score = int(result.get("score", 0))
    reasoning = result.get("reasoning") or ""
    strengths = result.get("strengths") or []
    gaps = result.get("gaps") or []

    # Update matches.match_reasoning (+ match_score only if explicitly asked).
    update_fields: dict[str, Any] = {
        "match_reasoning": reasoning,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if update_score:
        update_fields["match_score"] = round(score / 100.0, 4)
    try:
        await supabase.table("matches").update(update_fields).eq("id", match_id).execute()
    except Exception as e:
        return {"status": "error", "reason": f"matches update failed: {e}"}

    # Fresh find_match log so the modal/endpoint pulls corrected strengths/gaps.
    try:
        await supabase.table("agent_logs").insert(
            {
                "agent_code": agent_code,
                "action": "find_match",
                "related_candidate_id": candidate_id,
                "related_job_id": job_id,
                "related_match_id": match_id,
                "milestone": "clearance_reasoning_backfilled",
                "status": "success",
                "input_payload": {
                    "candidate_id": candidate_id,
                    "job_id": job_id,
                    "backfill": True,
                    "reason": "clearance_logic_fix",
                },
                "output_payload": {
                    "score": score,
                    "reasoning": reasoning,
                    "strengths": strengths,
                    "gaps": gaps,
                    "match_status": match.get("current_state") or "found",
                    "milestone": "clearance_reasoning_backfilled",
                    "clearance_relevant": relevant,
                    "llm_model": "claude-sonnet-4-5",
                    "tokens_used": int(result.get("tokens_used") or 0),
                    "duration_ms": int(result.get("duration_ms") or 0),
                },
                "reasoning": f"[CLEARANCE-BACKFILL] score={score}: {reasoning}",
            }
        ).execute()
    except Exception as e:
        return {"status": "error", "reason": f"agent_logs insert failed: {e}"}

    return {
        "status": "ok",
        "score": score,
        "strengths": len(strengths),
        "gaps": len(gaps),
        "tokens": result.get("tokens_used"),
    }


async def main(args: argparse.Namespace) -> int:
    supabase = await get_supabase_client()
    claude = AnthropicClient(api_key=settings.ANTHROPIC_API_KEY)
    matcher = AgentMatchingWorker(supabase_client=supabase, claude_client=claude)

    # Pull valid matches joined with the two clearance columns so we can filter
    # to clearance-relevant rows without a per-row fetch. PostgREST caps a
    # single response at 1000 rows, so page through with .range() until drained.
    PAGE = 1000
    matches: list[dict] = []
    page_start = 0
    while True:
        query = supabase.table("matches").select(
            "id, candidate_id, job_id, matched_by_agent_code, current_state, "
            "candidates(clearance_level), jobs(job_security_clearance)"
        ).eq("is_valid", True)
        if args.agent:
            query = query.eq("matched_by_agent_code", args.agent)
        resp = await query.order("id").range(page_start, page_start + PAGE - 1).execute()
        batch = resp.data or []
        matches.extend(batch)
        if len(batch) < PAGE:
            break
        page_start += PAGE
    logger.info("Found %d valid matches", len(matches))

    targets: list[dict] = []
    skipped_irrelevant = 0
    for m in matches:
        cand = m.get("candidates") or {}
        job = m.get("jobs") or {}
        if not args.all and not _clearance_relevant(cand, job):
            skipped_irrelevant += 1
            continue
        targets.append(m)
        if args.limit and len(targets) >= args.limit:
            break

    logger.info(
        "Clearance-relevant targets: %d  (skipped %d non-clearance, --all=%s, limit=%s)",
        len(targets), skipped_irrelevant, args.all, args.limit,
    )

    if args.dry_run:
        logger.info("--dry-run set, exiting before any Claude calls.")
        for m in targets:
            cand = m.get("candidates") or {}
            job = m.get("jobs") or {}
            logger.info(
                "  WOULD process %s  agent=%s  cand=%r  job=%r",
                m["id"], m.get("matched_by_agent_code"),
                cand.get("clearance_level"), job.get("job_security_clearance"),
            )
        return 0

    stats = {"ok": 0, "skip": 0, "error": 0}
    for i, m in enumerate(targets, 1):
        logger.info("[%d/%d] match=%s agent=%s …", i, len(targets), m["id"], m.get("matched_by_agent_code"))
        outcome = await backfill_one(matcher, supabase, m, update_score=args.update_score)
        stats[outcome["status"]] = stats.get(outcome["status"], 0) + 1
        if outcome["status"] == "ok":
            logger.info("    ✓ score=%s strengths=%s gaps=%s tokens=%s",
                        outcome["score"], outcome["strengths"], outcome["gaps"], outcome.get("tokens"))
        else:
            logger.warning("    %s: %s", outcome["status"].upper(), outcome.get("reason"))

    logger.info("Done. stats=%s", stats)
    return 0 if stats["error"] == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Show what would be processed, don't call Claude")
    p.add_argument("--limit", type=int, default=None, help="Process at most N matches")
    p.add_argument("--agent", type=str, default=None, help="Only backfill for this agent_code (e.g. naama)")
    p.add_argument("--all", action="store_true", help="Re-score every valid match, not just clearance-relevant ones")
    p.add_argument("--update-score", action="store_true", help="Also overwrite match_score (state is still left untouched)")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args)))
