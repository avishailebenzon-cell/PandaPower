"""Local (Claude-free) match backfill — populate the pipeline end-to-end.

Anthropic is over its usage limit, so the real Claude scorer can't run. This
script scores every candidate against every open job using ONLY data already
extracted (skills / experience / clearance / qualifications), applies Carmit's
rule-based gates INLINE (no Pipedrive writes), and inserts match rows with their
final state so the whole flow is visible:

  evaluated_but_rejected  (score < 70)         — agent looked, not a match
  carmit_rejected         (>=70 but failed a gate)
  sent_to_tal             (>=70 and passed gates) — flows to Tal

Run dry first:   python scripts/backfill_matches_local.py --dry-run
Then for real:   python scripts/backfill_matches_local.py
"""

import asyncio
import re
import sys

from pandapower.core.supabase import get_supabase_client
from pandapower.workers.agent_matching import AGENT_CONFIGS

DRY_RUN = "--dry-run" in sys.argv

# Thresholds (tuned after the dry-run histogram).
PASS_THRESHOLD = 60        # >=60 is a viable match (is_passing)
CARMIT_APPROVE_SCORE = 70  # Carmit quality-score gate
BATCH = 500

_TOKEN_RE = re.compile(r"[A-Za-z֐-׿][A-Za-z0-9֐-׿\+\#\.]{1,}")
_STOP = {
    "and", "the", "for", "with", "experience", "ניסיון", "שנות", "שנים", "של",
    "עם", "או", "את", "לפחות", "הכרות", "יתרון", "ידע", "יכולת", "עבודה",
    "level", "years", "able", "work", "knowledge",
}


def toks(*parts) -> set:
    out = set()
    for p in parts:
        if not p:
            continue
        if isinstance(p, (list, tuple)):
            p = " ".join(str(x) for x in p)
        elif isinstance(p, dict):
            p = " ".join(str(v) for v in p.values())
        for m in _TOKEN_RE.findall(str(p).lower()):
            if m not in _STOP and len(m) >= 2:
                out.add(m)
    return out


def clearance_level(val) -> int:
    """Map a clearance string to 0-3. 0 = none/unknown."""
    if not val:
        return 0
    s = str(val).lower()
    if any(x in s for x in ["ללא", "none", "no "]):
        return 0
    m = re.search(r"(\d)", s)
    if m:
        return min(3, int(m.group(1)))
    # Words implying real clearance.
    if any(x in s for x in ["secret", "high", "מסווג", "גבוה", "שוס"]):
        return 2
    return 0


def cand_tokens(c: dict) -> set:
    ef = (c.get("extracted_from_cv") or {}).get("extracted_fields", {}) or {}
    exp = c.get("experiences") or ef.get("experience") or []
    positions = [e.get("position") for e in exp if isinstance(e, dict)]
    return toks(
        c.get("key_skills"), ef.get("technical_skills"), ef.get("soft_skills"),
        ef.get("summary"), positions, c.get("top_education"), ef.get("education"),
    )


def job_tokens(j: dict) -> set:
    return toks(j.get("job_title"), j.get("job_qualifications"), j.get("job_description"))


def score_pair(c: dict, c_tok: set, c_clr: int, c_yrs, j: dict, j_tok: set, j_clr: int,
               dom_tok: set) -> tuple[int, str, int]:
    """Return (score 0-100, reasoning, total_overlap_count).

    Signals: domain-affinity (candidate skills vs the agent's domain keywords)
    is the primary signal — that's the match the system is meant to find — plus
    a bonus for overlap with the specific job text, experience and clearance.
    """
    # Domain affinity (0-45): candidate skills vs agent domain keywords.
    dom_hits = c_tok & dom_tok
    dom_score = min(45, len(dom_hits) * 14)

    # Specific-job overlap (0-30).
    job_hits = c_tok & j_tok
    job_score = min(30, len(job_hits) * 5)

    # Experience (0-15).
    yrs = c_yrs if isinstance(c_yrs, (int, float)) else 0
    exp_score = min(15, int(yrs * 2))

    # Clearance (0-10).
    if j_clr == 0 or c_clr >= j_clr:
        clr_score = 10
    elif c_clr > 0:
        clr_score = 5
    else:
        clr_score = 0

    score = max(0, min(100, dom_score + job_score + exp_score + clr_score))

    matched = sorted(dom_hits | job_hits)[:6]
    reasoning = (
        f"ניקוד מקומי {score}/100 (התאמה ראשונית ללא Claude). "
        f"זיקת-תחום: {len(dom_hits)} | חפיפה למשרה: {len(job_hits)} "
        f"({', '.join(matched) if matched else 'אין'}). "
        f"ניסיון: {yrs} שנים. "
        f"סיווג: מועמד רמה {c_clr} מול דרישת רמה {j_clr} "
        f"({'תואם' if (j_clr == 0 or c_clr >= j_clr) else 'חסר'})."
    )
    return score, reasoning, len(dom_hits) + len(job_hits)


def decide_state(score: int, c_clr: int, j_clr: int, overlap_n: int) -> tuple[str, bool]:
    """Apply Carmit's rule-based gates inline. Returns (state, is_passing)."""
    if score < PASS_THRESHOLD:
        return "evaluated_but_rejected", False
    # Gates (clearance + quality score + has relevant skills).
    clearance_ok = (j_clr == 0) or (c_clr >= j_clr)
    score_ok = score >= CARMIT_APPROVE_SCORE
    skills_ok = overlap_n > 0
    if clearance_ok and score_ok and skills_ok:
        return "sent_to_tal", True          # passed Carmit → flows to Tal
    return "carmit_rejected", True          # viable but Carmit gate rejected


async def main():
    sb = await get_supabase_client()

    # Open jobs.
    jobs = (await sb.table("jobs").select(
        "id, job_title, job_qualifications, job_description, job_security_clearance, "
        "assigned_agent_code"
    ).eq("status", "open").execute()).data or []
    # Per-agent domain keyword tokens (the primary affinity signal).
    dom_tokens = {}
    for code, cfg in AGENT_CONFIGS.items():
        t = toks(cfg.get("keywords"), cfg.get("domain"))
        # gc = "general / any domain" → no meaningful keywords; leave empty.
        dom_tokens[code] = set() if code == "gc" else t

    for j in jobs:
        j["_tok"] = job_tokens(j)
        j["_clr"] = clearance_level(j.get("job_security_clearance"))
    print(f"open jobs: {len(jobs)}")

    # Candidates (paginated).
    cands, off = [], 0
    while True:
        b = (await sb.table("candidates").select(
            "id, name, clearance_level, years_of_experience, key_skills, "
            "experiences, top_education, extracted_from_cv"
        ).is_("deleted_at", "null").range(off, off + 999).execute()).data or []
        cands.extend(b)
        if len(b) < 1000:
            break
        off += 1000
    for c in cands:
        c["_tok"] = cand_tokens(c)
        c["_clr"] = clearance_level(c.get("clearance_level"))
    print(f"candidates: {len(cands)}")

    # Existing (candidate_id, job_id) pairs to skip.
    existing = set()
    off = 0
    while True:
        b = (await sb.table("matches").select("candidate_id, job_id").range(off, off + 999).execute()).data or []
        existing.update((r["candidate_id"], r["job_id"]) for r in b)
        if len(b) < 1000:
            break
        off += 1000
    print(f"existing matches to skip: {len(existing)}\n")

    rows = []
    from collections import Counter
    state_counts = Counter()
    score_hist = Counter()

    for j in jobs:
        agent = j.get("assigned_agent_code") or "gc"
        dtok = dom_tokens.get(agent, set())
        for c in cands:
            if (c["id"], j["id"]) in existing:
                continue
            score, reasoning, overlap_n = score_pair(
                c, c["_tok"], c["_clr"], c.get("years_of_experience"),
                j, j["_tok"], j["_clr"], dtok)
            state, passing = decide_state(score, c["_clr"], j["_clr"], overlap_n)
            state_counts[state] += 1
            score_hist[(score // 10) * 10] += 1
            rows.append({
                "candidate_id": c["id"],
                "job_id": j["id"],
                "match_score": round(score / 100.0, 4),
                "evaluated_score_raw": score,
                "is_passing": passing,
                "is_valid": True,
                "current_state": state,
                "matched_by_agent_code": agent,
                "match_reasoning": reasoning,
                "state_updated_by_agent": agent,
            })

    print(f"total new evaluations: {len(rows)}")
    print("\nscore histogram (bucket → count):")
    for b in sorted(score_hist):
        print(f"  {b:3d}-{b+9}: {score_hist[b]}")
    print("\nfinal-state distribution:")
    for s, n in state_counts.most_common():
        print(f"  {s}: {n}")
    # Per-agent sent_to_tal preview
    tal = Counter(r["matched_by_agent_code"] for r in rows if r["current_state"] == "sent_to_tal")
    print("\nsent_to_tal per agent:", dict(tal))

    if DRY_RUN:
        print("\n[DRY RUN] nothing written.")
        return

    print(f"\nInserting {len(rows)} rows in batches of {BATCH}...")
    inserted, failed = 0, 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        try:
            await sb.table("matches").insert(chunk).execute()
            inserted += len(chunk)
        except Exception as e:
            failed += len(chunk)
            print(f"  batch {i//BATCH} failed: {str(e)[:120]}")
        if (i // BATCH) % 10 == 0:
            print(f"  {inserted}/{len(rows)} inserted ({failed} failed)")
    print(f"\n✅ inserted {inserted} matches ({failed} failed)")

    total = (await sb.table("matches").select("id", count="exact").limit(1).execute()).count
    print(f"matches table total now: {total}")


if __name__ == "__main__":
    asyncio.run(main())
