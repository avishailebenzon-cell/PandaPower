-- Phase 4A: Add job change detection fields to jobs table
-- Enables tracking of job specification changes and automatic re-matching
-- Hash is computed from critical fields: priority, title, description, qualifications, requirements, location, etc.

-- Add columns to jobs table for change detection
ALTER TABLE jobs
ADD COLUMN job_spec_hash TEXT DEFAULT NULL,
ADD COLUMN spec_last_hash_computed_at TIMESTAMPTZ DEFAULT NULL,
ADD COLUMN last_modified_by TEXT DEFAULT NULL;

-- Create index on job_spec_hash for change detection queries
CREATE INDEX idx_jobs_spec_hash ON jobs(job_spec_hash)
WHERE job_spec_hash IS NOT NULL;

-- Create index on spec_last_hash_computed_at for diagnostics
CREATE INDEX idx_jobs_spec_computed_at ON jobs(spec_last_hash_computed_at DESC)
WHERE spec_last_hash_computed_at IS NOT NULL;

-- Create index on last_modified_by for auditing
CREATE INDEX idx_jobs_modified_by ON jobs(last_modified_by)
WHERE last_modified_by IS NOT NULL;

-- Add comments documenting the new fields
COMMENT ON COLUMN jobs.job_spec_hash IS 'SHA256 hash of critical job specification fields: priority, title, description, qualifications, requirements, location, required_experience_years, seniority_level, salary_min, salary_max. When hash changes, all existing matches become invalid and re-matching is triggered.';
COMMENT ON COLUMN jobs.spec_last_hash_computed_at IS 'Timestamp when job_spec_hash was last computed. Used for auditing and understanding when job specs last changed.';
COMMENT ON COLUMN jobs.last_modified_by IS 'Who last modified this job and triggered a re-hash: "pipedrive_sync", user_id, or "api_endpoint". Helps with audit trail.';
