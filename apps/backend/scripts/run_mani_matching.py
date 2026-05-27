"""Mani — independent Level-1 clearance matcher.

The 7 domain agents (Alik / Naama / Dganit / Ofir / Itai / Lior / GC) are
routed jobs by Carmit. Mani is different: he works on his own, with a
single rule:

    Whenever a Level-1-clearance candidate exists alongside a Level-1
    job, Mani is supposed to score the pair and surface the match in his
    own queue. No Carmit involvement, no quality gates other than the
    same Claude scoring call the other agents use.

This script is both:
  • a one-shot backfill — run it now to populate any pairs that were
    missed before Mani was wired up.
  • the body of the future periodic task — apply the same loop on a
    Celery beat schedule and you have ongoing operation. Idempotent:
    re-runs skip pairs that already have a Mani match.

Run from apps/backend:

    PYTHONPATH=src .venv/bin/python scripts/run_mani_matching.py
    PYTHONPATH=src .venv/bin/python scripts/run_mani_matching.py --dry-run

The set of "Level-1" values is defined below — kept generous so that
both Hebrew ("רמה 1", "רמה 1 + שוס") and English ("Level 1", "level 1")
are recognised on either side.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from typing import Any

sys.path.insert(0, "src")

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.workers.agent_matching import AGENT_CONFIGS, AgentMatchingWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("mani_matching")

# What counts as "Level 1" on the candidate side and on the job side.
# Lower-cased and stripped before comparing.
LEVEL_1_CAND_VALUES = {"רמה 1", "level 1", "1"}
LEVEL_1_JOB_VALUES = {"רמה 1", "רמה 1 + שוס", "level 1", "1"}

AGENT_CODE = "mani"


def _is_level_1_candidate(value: str | None) -> bool:
    if not value:
        return False
    return str(value).strip().lower() in {v.lower() for v in LEVEL_1_CAND_VALUES}


def _is_level_1_job(value: str | None) -> bool:
    if not value:
        return False
    return str(value).strip().lower() in {v.lower() for v in LEVEL_1_JOB_VALUES}


async def main(args: argparse.Namespace) -> int:
    supabase = await get_supabase_client()
    claude = AnthropicClient(api_key=settings.ANTHROPIC_API_KEY)
    matcher = AgentMatchingWorker(supabase_client=supabase, claude_client=claude)

    agent_config = AGENT_CONFIGS.get(AGENT_CODE)
    if not agent_config:
        logger.error("Mani is missing from AGENT_CONFIGS — add him before running.")
        return 1

    # Pull every candidate and every job — small data, this is fine.
    cands_resp = await supabase.table("candidates").select("*").execute()
    jobs_resp = await supabase.table("jobs").select("*").execute()
    candidates = [c for c in (cands_resp.data or []) if _is_level_1_candidate(c.get("clearance_level"))]
    jobs = [j for j in (jobs_resp.data or []) if _is_level_1_job(j.get("job_security_clearance"))]

    logger.info("Level-1 candidates: %d", len(candidates))
    logger.info("Level-1 jobs      : %d", len(jobs))
    logger.info("Pairs to consider : %d", len(candidates) * len(jobs))

    if not candidates or not jobs:
        logger.warning("Nothing to match — at least one side is empty.")
        return 0

    # Find existing Mani matches so we can skip pairs already done.
    existing_resp = await supabase.table("matches").select(
        "candidate_id, job_id"
    ).eq("matched_by_agent_code", AGENT_CODE).execute()
    already_done: set[tuple[str, str]] = {
        (str(m["candidate_id"]), str(m["job_id"])) for m in (existing_resp.data or [])
    }
    logger.info("Pairs already done: %d", len(already_done))

    todo = [
        (c, j) for c in candidates for j in jobs
        if (str(c["id"]), str(j["id"])) not in already_done
    ]
    logger.info("Pairs to process  : %d", len(todo))

    if args.dry_run:
        for c, j in todo[:20]:
            logger.info(
                "  WOULD score cand=%s (clearance=%r) × job=%r (req=%r)",
                c.get("name") or c["id"],
                c.get("clearance_level"),
                j.get("job_title"),
                j.get("job_security_clearance"),
            )
        if len(todo) > 20:
            logger.info("  ... and %d more", len(todo) - 20)
        return 0

    stats = {"ok": 0, "skip": 0, "error": 0}
    for i, (candidate, job) in enumerate(todo, 1):
        cand_name = candidate.get("name") or candidate["id"]
        job_title = job.get("job_title") or job["id"]
        logger.info("[%d/%d] cand=%s × job=%r", i, len(todo), cand_name, job_title)
        try:
            scored = await matcher._score_candidate_job_pair(
                candidate, job, AGENT_CODE, agent_config
            )
            await matcher._create_match(
                candidate_id=candidate["id"],
                job_id=job["id"],
                score=int(scored.get("score") or 0),
                reasoning=scored.get("reasoning") or "",
                strengths=scored.get("strengths") or [],
                gaps=scored.get("gaps") or [],
                agent_code=AGENT_CODE,
                tokens_used=int(scored.get("tokens_used") or 0),
                duration_ms=float(scored.get("duration_ms") or 0.0),
            )
            stats["ok"] += 1
            logger.info(
                "    ✓ score=%s  strengths=%d gaps=%d",
                scored.get("score"),
                len(scored.get("strengths") or []),
                len(scored.get("gaps") or []),
            )
        except Exception as e:
            stats["error"] += 1
            logger.warning("    ERROR: %s", str(e)[:200])

    logger.info("Done. stats=%s", stats)
    return 0 if stats["error"] == 0 else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Show plan, don't call Claude")
    args = p.parse_args()
    sys.exit(asyncio.run(main(args)))
