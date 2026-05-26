-- Migration: Update jobs table schema to include job-specific fields
-- This replaces the old jobs table with the new schema that includes:
-- - job_title, job_description, job_qualifications, job_location, job_security_clearance
-- - deadline, priority, classification_level
-- - Filters to only sync open deals with job_title

-- Drop old indexes
DROP INDEX IF EXISTS idx_jobs_pipedrive_id;
DROP INDEX IF EXISTS idx_jobs_status;
DROP INDEX IF EXISTS idx_jobs_person_id;
DROP INDEX IF EXISTS idx_jobs_job_title;

-- Drop and recreate the table with new schema
DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipedrive_deal_id INT UNIQUE,
    job_title TEXT NOT NULL,
    job_description TEXT,
    job_qualifications TEXT,
    job_location TEXT,
    job_security_clearance TEXT,
    deadline DATE,
    priority TEXT,
    classification_level TEXT,
    person_id INT,
    org_id INT,
    stage_id INT,
    status TEXT DEFAULT 'open',
    pipedrive_last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create new indexes for performance
CREATE INDEX idx_jobs_pipedrive_id ON jobs(pipedrive_deal_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_person_id ON jobs(person_id);
CREATE INDEX idx_jobs_job_title ON jobs(job_title);

-- Verify table was created
SELECT * FROM jobs LIMIT 0;
