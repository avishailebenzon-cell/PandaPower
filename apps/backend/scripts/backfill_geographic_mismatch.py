"""One-time backfill: flag geographic mismatch on EXISTING matches.

New matches get a geographic_mismatch flag set by the matching worker
(agent_matching.py) — Claude judges whether the candidate's location allows a
reasonable daily commute to the job's location. This script applies the same
judgement to matches that were created BEFORE that change, so the bold red
"אין התאמה גיאוגרפית" badge shows up retroactively in every match table.

The match is never dropped — only flagged — because some candidates relocate.

Logic:
  • Only matches that have BOTH a candidate location AND a job location are
    evaluated (no location on either side → cannot judge → left as-is/false).
  • Same city / metro area → not a mismatch. Impractical daily commute
    (~>60-70 km or ~>1.5h each way) → mismatch, with a short Hebrew reason.
  • The professional match score is NOT touched — geography is separate.

Usage:
    python -m scripts.backfill_geographic_mismatch            # apply
    python -m scripts.backfill_geographic_mismatch --dry-run  # preview only
    python -m scripts.backfill_geographic_mismatch --valid-only  # is_valid=True only

NOTE: requires Anthropic API access. If the account is over its usage limit the
calls will fail — run this once the limit is lifted. Uses the cheap Haiku model.
"""

import asyncio
import sys

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient

DRY_RUN = "--dry-run" in sys.argv
VALID_ONLY = "--valid-only" in sys.argv

GEO_SYSTEM = (
    "You are a recruitment geography assistant for the Israeli job market. "
    "Given a candidate's home location and a job's location (both in Israel), "
    "decide whether a daily commute between them is impractical — roughly more "
    "than ~60-70 km or ~1.5 hours each way. Same city, neighboring cities, or "
    "the same metropolitan area (Gush Dan, the Sharon, greater Jerusalem, "
    "greater Haifa, etc.) are NOT a mismatch. "
    'Respond ONLY with valid JSON: '
    '{"geographic_mismatch": true|false, '
    '"geographic_reason": "<אם true: משפט קצר בעברית עם הערים והמרחק המשוער; אם false: מחרוזת ריקה>"}'
)


async def _judge(client: AnthropicClient, cand_loc: str, job_loc: str) -> dict:
    prompt = (
        f"מיקום המועמד: {cand_loc}\n"
        f"מיקום המשרה: {job_loc}\n\n"
        "האם יש אי-התאמה גיאוגרפית (נסיעה יומית לא סבירה)?"
    )
    data = await client._make_request_with_retry(
        messages=[{"role": "user", "content": prompt}],
        system=GEO_SYSTEM,
    )
    parsed = client._extract_json(
        "".join(
            p.get("text", "")
            for p in (data.get("content", []) or [])
            if p.get("type") == "text"
        )
    )
    return {
        "geographic_mismatch": bool(parsed.get("geographic_mismatch", False)),
        "geographic_reason": (parsed.get("geographic_reason") or "").strip() or None,
    }


async def main():
    sb = await get_supabase_client()
    client = AnthropicClient(settings.ANTHROPIC_API_KEY)
    client.usage_stage = "backfill_geographic"
    client.model = "claude-haiku-4-5"  # cheap judgement

    # Page through matches, joining candidate + job location.
    rows = []
    offset = 0
    while True:
        q = sb.table("matches").select(
            "id, is_valid, geographic_mismatch, "
            "candidates(location), jobs(job_location)"
        )
        if VALID_ONLY:
            q = q.eq("is_valid", True)
        r = await q.range(offset, offset + 999).execute()
        batch = r.data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000

    def _loc(obj, *keys):
        if not isinstance(obj, dict):
            return None
        for k in keys:
            if obj.get(k):
                return obj.get(k)
        return None

    candidates = []
    for row in rows:
        cand_loc = _loc(row.get("candidates"), "location")
        job_loc = _loc(row.get("jobs"), "job_location", "location")
        if cand_loc and job_loc and str(cand_loc).strip() and str(job_loc).strip():
            candidates.append((row["id"], str(cand_loc).strip(), str(job_loc).strip()))

    print(f"Total matches scanned: {len(rows)}")
    print(f"Have both locations (evaluable): {len(candidates)}")

    if DRY_RUN:
        for mid, c, j in candidates[:15]:
            print(f"  - {mid}: '{c}'  →  '{j}'")
        print("(dry-run, no Claude calls, no changes written)")
        await client.close()
        return

    flagged = 0
    done = 0
    for mid, cand_loc, job_loc in candidates:
        try:
            res = await _judge(client, cand_loc, job_loc)
            await sb.table("matches").update(
                {
                    "geographic_mismatch": res["geographic_mismatch"],
                    "geographic_mismatch_reason": res["geographic_reason"],
                }
            ).eq("id", mid).execute()
            done += 1
            if res["geographic_mismatch"]:
                flagged += 1
                print(f"  📍 {mid}: {cand_loc} → {job_loc} | {res['geographic_reason']}")
            if done % 25 == 0:
                print(f"  processed {done}/{len(candidates)} ({flagged} flagged)")
        except Exception as e:
            print(f"  FAILED {mid}: {e}")

    print(f"Done. Processed {done}/{len(candidates)}; flagged {flagged} as geographic mismatch.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
