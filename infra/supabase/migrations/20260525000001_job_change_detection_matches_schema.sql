-- Phase 4A: Add job change detection fields to matches table
-- Enables tracking of match validity based on job specification changes
-- When a job is modified (priority, description, qualifications, etc.),
-- matches can be marked invalid and re-evaluated with new job specs

-- Add columns to matches table for change detection and invalidation
ALTER TABLE matches
ADD COLUMN is_valid BOOLEAN DEFAULT TRUE,
ADD COLUMN invalidated_at TIMESTAMPTZ DEFAULT NULL,
ADD COLUMN invalidation_reason TEXT DEFAULT NULL,
ADD COLUMN invalidated_by TEXT DEFAULT NULL,
ADD COLUMN last_job_spec_check_at TIMESTAMPTZ DEFAULT NULL,
ADD COLUMN job_spec_hash_at_match_creation TEXT DEFAULT NULL;

-- Create index on is_valid for efficient filtering
CREATE INDEX idx_matches_valid ON matches(is_valid)
WHERE is_valid = FALSE;

-- Create composite index for finding invalid matches by job
CREATE INDEX idx_matches_job_valid ON matches(job_id, is_valid)
WHERE is_valid = FALSE;

-- Create index on invalidation reason for analytics
CREATE INDEX idx_matches_invalidation_reason ON matches(invalidation_reason)
WHERE invalidation_reason IS NOT NULL;

-- Create index on last_job_spec_check_at for auditing
CREATE INDEX idx_matches_spec_check ON matches(last_job_spec_check_at DESC)
WHERE last_job_spec_check_at IS NOT NULL;

-- Add comment documenting the new fields
COMMENT ON COLUMN matches.is_valid IS 'FALSE if match has been invalidated due to job specification change. Check invalidated_at and invalidation_reason for details.';
COMMENT ON COLUMN matches.invalidated_at IS 'Timestamp when match was invalidated. NULL if match is still valid.';
COMMENT ON COLUMN matches.invalidation_reason IS 'Reason match was invalidated: "specs_changed", "priority_increased", "manual_rematch_request", etc. NULL if match is still valid.';
COMMENT ON COLUMN matches.invalidated_by IS 'Who invalidated the match: "system", "pipedrive_sync", user_id, or agent_code. NULL if match is still valid.';
COMMENT ON COLUMN matches.last_job_spec_check_at IS 'Last timestamp when job specification was checked against this match. Helps audit trail and debugging.';
COMMENT ON COLUMN matches.job_spec_hash_at_match_creation IS 'SHA256 hash of critical job fields (priority, title, description, etc.) at time match was created. Enables validation that match was created with current job spec.';
