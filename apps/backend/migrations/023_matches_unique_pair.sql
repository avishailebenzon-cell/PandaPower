-- 023_matches_unique_pair.sql
-- Close the agent_match cost leak: guarantee one match row per (candidate, job).
--
-- WHY: agent_matching dedups by reading existing matches rows. With no unique
-- constraint, any failed/duplicate insert leaves a pair "unmatched", so the next
-- scheduler cycle re-scores it with Claude (Sonnet) again — forever. During the
-- historical backfill this compounded into ~10k Claude calls/day (~$185/day).
-- A UNIQUE(candidate_id, job_id) lets _create_match upsert with ON CONFLICT DO
-- NOTHING, so a pair is scored at most once.

BEGIN;

-- 1) Collapse any existing duplicate pairs, keeping the most informative row:
--    prefer a passing match, then the highest raw score, then the newest.
WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY candidate_id, job_id
            ORDER BY
                is_passing DESC NULLS LAST,
                evaluated_score_raw DESC NULLS LAST,
                state_updated_at DESC NULLS LAST,
                id DESC
        ) AS rn
    FROM matches
    WHERE candidate_id IS NOT NULL AND job_id IS NOT NULL
)
DELETE FROM matches m
USING ranked r
WHERE m.id = r.id
  AND r.rn > 1;

-- 2) Enforce one row per pair going forward.
ALTER TABLE matches
    ADD CONSTRAINT matches_candidate_job_unique UNIQUE (candidate_id, job_id);

COMMIT;
