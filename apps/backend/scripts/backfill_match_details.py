"""Backfill strengths / gaps / reasoning for existing matches.

The new "מפרט" modal in the agent screens reads three things per match:
  • matches.match_reasoning  (a free-text explanation, stored on the row)
  • agent_logs.output_payload.strengths  (list of why-fits)
  • agent_logs.output_payload.gaps       (list of why-doesn't-fit)
all of which are produced by AgentMatchingWorker._score_candidate_job_pair
when a NEW match is created. Matches that pre-date this code have nothing
to show in the modal, so this script re-scores them using the very same
Claude call and writes the results back idempotently.

Run from apps/backend:

    PYTHONPATH=src .venv/bin/python scripts/backfill_match_details.py
    PYTHONPATH=src .venv/bin/python scripts/backfill_match_details.py --dry-run
    PYTHONPATH=src .venv/bin/python scripts/backfill_match_details.py --limit 5
    PYTHONPATH=src .venv/bin/python scripts/backfill_match_details.py --agent naama

Idempotent: a match is skipped if it already has a match_reasoning AND
a find_match log with non-empty strengths/gaps. So re-running won't pay
the API cost twice for the same row.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Any

# Allow running as `python scripts/backfill_match_details.py`
sys.path.insert(0, "src")

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.workers.agent_matching import AgentMatchingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("backfill_match_details")


async def already_has_details(supabase, match_row: dict[str, Any]) -> bool:
    """Skip a match that already has reasoning AND a non-empty find_match log."""
    if not match_row.get("match_reasoning"):
        return False
    log_resp = await supabase.table("agent_logs").select(
        "output_payload"
    ).eq("related_match_id", match_row["id"]).eq("action", "find_match").limit(1).execute()
    if not log_resp.data:
        return False
    payload = log_resp.data[0].get("output_payload") or {}
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("strengths") or payload.get("gaps"))


async def backfill_one(matcher: AgentMatchingWorker, supabase, match: dict) -> dict:
    """Score and persist a single match. Returns {'status': 'ok'|'skip'|'error', ...}."""
    match_id = match["id"]
    candidate_id = match.get("candidate_id")
    job_id = match.get("job_id")
    agent_code = match.get("matched_by_agent_code")

    if not candidate_id or not job_id or not agent_code:
        return {"status": "skip", "reason": "missing candidate/job/agent on match"}

    # 1. Fetch candidate and job rows
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

    # 2. Get the agent's matching config (domain / keywords / persona)
    agent_config = matcher._get_agent_config(agent_code)
    if not agent_config:
        return {"status": "skip", "reason": f"no agent_config for {agent_code!r}"}

    # 3. Call Claude (same code path the worker uses for new matches)
    try:
        result = await matcher._score_candidate_job_pair(candidate, job, agent_code, agent_config)
    except Exception as e:
        return {"status": "error", "reason": f"Claude scoring failed: {e}"}

    score = int(result.get("score", 0))
    reasoning = result.get("reasoning") or ""
    strengths = result.get("strengths") or []
    gaps = result.get("gaps") or []

    # 4. Write back to matches.match_reasoning (and refresh updated_at)
    try:
        await supabase.table("matches").update(
            {
                "match_reasoning": reasoning,
                "updated_at": datetime.utcnow().isoformat(),
            }
        ).eq("id", match_id).execute()
    except Exception as e:
        return {"status": "error", "reason": f"matches update failed: {e}"}

    # 5. Insert a find_match log so the new endpoint can pull strengths/gaps.
    # NOTE: production agent_logs table has fewer columns than the migration
    # suggests — duration_ms / tokens_used / llm_model are NOT present. Keep
    # this insert to the verified column set only. We stash the model/timing
    # data inside output_payload instead, so nothing is lost.
    try:
        await supabase.table("agent_logs").insert(
            {
                "agent_code": agent_code,
                "action": "find_match",
                "related_candidate_id": candidate_id,
                "related_job_id": job_id,
                "related_match_id": match_id,
                "milestone": "candidate_match_backfilled",
                "status": "success",
                "input_payload": {"candidate_id": candidate_id, "job_id": job_id, "backfill": True},
                "output_payload": {
                    "score": score,
                    "reasoning": reasoning,
                    "strengths": strengths,
                    "gaps": gaps,
                    "match_status": match.get("current_state") or "found",
                    "milestone": "candidate_match_backfilled",
                    # extras that don't have dedicated columns
                    "llm_model": "claude-sonnet-4-5",
                    "tokens_used": int(result.get("tokens_used") or 0),
                    "duration_ms": int(result.get("duration_ms") or 0),
                },
                "reasoning": f"[BACKFILL] score={score}: {reasoning}",
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

    # Pull every valid match (and the few rows we need)
    query = supabase.table("matches").select(
        "id, candidate_id, job_id, matched_by_agent_code, current_state, match_reasoning"
    ).eq("is_valid", True)
    if args.agent:
        query = query.eq("matched_by_agent_code", args.agent)
    resp = await query.execute()
    matches = resp.data or []
    logger.info("Found %d valid matches", len(matches))

    # Filter: keep only those that don't already have details
    targets: list[dict] = []
    for m in matches:
        if await already_has_details(supabase, m):
            continue
        targets.append(m)
        if args.limit and len(targets) >= args.limit:
            break
    logger.info("Need backfill: %d (limit=%s)", len(targets), args.limit)

    if args.dry_run:
        logger.info("--dry-run set, exiting before any Claude calls.")
        for m in targets:
            logger.info("  WOULD process %s  agent=%s  state=%s",
                        m["id"], m["matched_by_agent_code"], m.get("current_state"))
        return 0

    stats = {"ok": 0, "skip": 0, "error": 0}
    for i, m in enumerate(targets, 1):
        logger.info("[%d/%d] match=%s agent=%s …", i, len(targets), m["id"], m["matched_by_agent_code"])
        outcome = await backfill_one(matcher, supabase, m)
        stats[outcome["status"]] = stats.get(outcome["status"], 0) + 1
        if outcome["status"] == "ok":
            logger.info("    ✓ score=%s  strengths=%s gaps=%s tokens=%s",
                        outcome["score"], outcome["strengths"], outcome["gaps"], outcome.get("tokens"))
        else:
            logger.warning("    %s: %s", outcome["status"].upper(), outcome.get("reason"))

    logger.info("Done. stats=%s", stats)
    return 0 if stats["error"] == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Show what would be processed, don't call Claude")
    p.add_argument("--limit", type=int, default=None, help="Process at most N matches")
    p.add_argument("--agent", type=str, default=None, help="Only backfill for this agent_code (e.g. naama)")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args)))
