-- Migration 010: Add candidate_extracted_at cursor to cv_files
--
-- BUG FIXED: The candidate-creation worker queried
--   cv_files WHERE parse_status='success' AND is_latest=true LIMIT 20
-- with NO ordering and NO "already processed" marker. PostgREST returned the
-- SAME 20 rows every run, so the worker re-UPDATEd the same ~20 candidates
-- every 4 minutes and NEVER advanced through the backlog. Result: 1,200+
-- successfully-parsed CVs were stuck and only ~49 candidates existed.
--
-- This column is the processing cursor: the worker stamps candidate_extracted_at
-- on EVERY CV it attempts (created / updated / skipped-low-confidence / no-name),
-- then filters `WHERE candidate_extracted_at IS NULL`. This guarantees forward
-- progress and prevents unparseable CVs from blocking the queue.

ALTER TABLE cv_files
ADD COLUMN IF NOT EXISTS candidate_extracted_at TIMESTAMPTZ;

-- Backfill: any CV already linked to a candidate has effectively been processed.
UPDATE cv_files
SET candidate_extracted_at = NOW()
WHERE id IN (SELECT cv_file_id FROM candidates WHERE cv_file_id IS NOT NULL)
  AND candidate_extracted_at IS NULL;

-- Partial index: the worker's hot query is
--   WHERE parse_status='success' AND is_latest=true AND candidate_extracted_at IS NULL
-- A partial index keeps it tiny (only the unprocessed rows) and fast.
CREATE INDEX IF NOT EXISTS idx_cv_files_candidate_pending
ON cv_files (created_at DESC)
WHERE parse_status = 'success' AND is_latest = true AND candidate_extracted_at IS NULL;
