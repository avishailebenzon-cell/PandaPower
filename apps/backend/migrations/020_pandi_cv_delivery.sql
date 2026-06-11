-- 020_pandi_cv_delivery.sql
-- Pandi end-to-end: shortlist -> client pick -> auto-send Panda-Tech CV.
--
-- 1. Give every candidate a stable, human-facing "iron number" (C000123). The
--    Pandi agent already references candidates.candidate_number but the column
--    never existed, so search/referral lookups silently failed. This adds it,
--    backfills existing rows by created_at, and auto-assigns it for new rows.
-- 2. Track the delivered Panda-Tech CV on the referral row.
--
-- Safe to run more than once (IF NOT EXISTS / idempotent backfill).

-- ---------------------------------------------------------------------------
-- 1) candidates.candidate_number  (C000001, C000002, ...)
-- ---------------------------------------------------------------------------
CREATE SEQUENCE IF NOT EXISTS candidate_number_seq;

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS candidate_number TEXT;

-- Backfill rows that don't have a number yet, oldest first.
WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY created_at NULLS LAST, id) AS rn
    FROM candidates
    WHERE candidate_number IS NULL
)
UPDATE candidates c
SET candidate_number = 'C' || LPAD(numbered.rn::text, 6, '0')
FROM numbered
WHERE c.id = numbered.id;

-- Advance the sequence past the highest backfilled number.
SELECT setval(
    'candidate_number_seq',
    GREATEST(
        (SELECT COALESCE(MAX(NULLIF(regexp_replace(candidate_number, '\D', '', 'g'), ''))::bigint, 0)
         FROM candidates),
        1
    )
);

-- Auto-assign for future inserts.
ALTER TABLE candidates
    ALTER COLUMN candidate_number
    SET DEFAULT 'C' || LPAD(nextval('candidate_number_seq')::text, 6, '0');

CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_candidate_number
    ON candidates (candidate_number);

-- ---------------------------------------------------------------------------
-- 2) candidate_referrals: store the delivered Panda-Tech CV
-- ---------------------------------------------------------------------------
ALTER TABLE candidate_referrals
    ADD COLUMN IF NOT EXISTS formatted_cv_path TEXT,
    ADD COLUMN IF NOT EXISTS full_cv_sent_at   TIMESTAMPTZ;
