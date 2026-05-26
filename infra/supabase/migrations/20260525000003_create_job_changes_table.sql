-- Phase 4A: Create job_changes history table for auditing job modifications
-- Complete audit trail of all changes to jobs and their impacts on matches
-- This enables:
-- 1. Understanding why matches were invalidated
-- 2. Reconstructing job history for compliance
-- 3. Analyzing frequency of job changes
-- 4. Tracking which fields change most often

CREATE TABLE job_changes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Job reference
  job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,

  -- Change metadata
  change_type TEXT NOT NULL,  -- "created", "modified", "priority_changed", "specs_changed", etc.
  changed_by TEXT NOT NULL,    -- "pipedrive_sync", "system", user_id, agent_code
  changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Change details
  previous_values JSONB DEFAULT '{}'::jsonb,  -- {priority: 2, description: "old text", ...}
  new_values JSONB DEFAULT '{}'::jsonb,       -- {priority: 1, description: "new text", ...}
  fields_changed TEXT[] DEFAULT ARRAY[]::TEXT[],  -- ["priority", "description", "qualifications"]

  -- Hash tracking
  job_spec_hash_before TEXT DEFAULT NULL,  -- Hash before change
  job_spec_hash_after TEXT DEFAULT NULL,   -- Hash after change

  -- Impact metrics
  affected_matches_count INT DEFAULT 0,    -- How many matches were invalidated by this change
  matches_in_protected_states INT DEFAULT 0,  -- Matches NOT invalidated (sent_to_tal, tal_approved)

  -- Audit trail
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient queries
CREATE INDEX idx_job_changes_job_id ON job_changes(job_id);
CREATE INDEX idx_job_changes_changed_at ON job_changes(changed_at DESC);
CREATE INDEX idx_job_changes_changed_by ON job_changes(changed_by);
CREATE INDEX idx_job_changes_change_type ON job_changes(change_type);
CREATE INDEX idx_job_changes_affected_matches ON job_changes(affected_matches_count DESC)
WHERE affected_matches_count > 0;

-- Composite index for auditing: "find all changes for a job, sorted by time"
CREATE INDEX idx_job_changes_job_time ON job_changes(job_id, changed_at DESC);

-- Composite index for impact analysis: "find high-impact changes"
CREATE INDEX idx_job_changes_type_impact ON job_changes(change_type, affected_matches_count DESC);

-- Add comments documenting the table and fields
COMMENT ON TABLE job_changes IS 'Complete audit trail of all changes to jobs. Records what changed, when it changed, who changed it, and what impact it had on existing matches. Essential for compliance, debugging, and analytics.';
COMMENT ON COLUMN job_changes.change_type IS 'Type of change: "created" (new job), "modified" (fields changed), "priority_changed" (special case), "specs_changed" (qualifications/requirements/location changed), etc.';
COMMENT ON COLUMN job_changes.changed_by IS 'Source of change: "pipedrive_sync" (automated from Pipedrive), "system" (automated re-match trigger), user_id (manual API), or agent_code (agent-initiated).';
COMMENT ON COLUMN job_changes.previous_values IS 'JSONB object with the values of changed fields BEFORE the change. Example: {priority: 2, description: "old job desc"}. Empty object if job was newly created.';
COMMENT ON COLUMN job_changes.new_values IS 'JSONB object with the values of changed fields AFTER the change. Example: {priority: 1, description: "new job desc"}.';
COMMENT ON COLUMN job_changes.fields_changed IS 'Array of field names that changed. Example: ["priority", "description", "qualifications"]. Used to understand scope of change.';
COMMENT ON COLUMN job_changes.job_spec_hash_before IS 'SHA256 hash of critical job fields BEFORE the change. Compare with job_spec_hash_after to determine if this was a spec-changing modification.';
COMMENT ON COLUMN job_changes.job_spec_hash_after IS 'SHA256 hash of critical job fields AFTER the change. If different from job_spec_hash_before, all matches for this job were invalidated.';
COMMENT ON COLUMN job_changes.affected_matches_count IS 'Number of matches that were invalidated due to this change. Metric for understanding frequency of re-matching work.';
COMMENT ON COLUMN job_changes.matches_in_protected_states IS 'Number of matches that were NOT invalidated because they were in protected states (sent_to_tal, tal_approved). These matches continued without re-evaluation.';
