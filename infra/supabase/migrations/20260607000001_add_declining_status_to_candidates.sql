-- Add declining_status to candidates so Carmit's Gate 2 (already_declined) works.
--
-- Carmit's _check_already_declined_gate reads candidates.declining_status and
-- treats it as a list of job IDs the candidate previously declined:
--
--     declining_status = candidate.get("declining_status", [])
--     if str(job_id) in [str(j) for j in declining_status]: reject
--
-- The column never existed in production, so the query raised
-- "column candidates.declining_status does not exist" (42703); the gate's
-- try/except swallowed the error and failed open, silently disabling the
-- dedupe-against-declines feature. JSONB array matches the read shape.

ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS declining_status JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN candidates.declining_status IS
    'List of job IDs (as strings) this candidate has declined. Read by Carmit Gate 2 (already_declined) to avoid re-presenting a declined job.';
