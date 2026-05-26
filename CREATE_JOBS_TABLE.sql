-- Run this SQL in Supabase SQL Editor to create the jobs table for Pipedrive deals

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipedrive_deal_id INT UNIQUE,
    title TEXT NOT NULL,
    value DECIMAL,
    currency TEXT,
    person_id INT,
    org_id INT,
    stage_id INT,
    probability DECIMAL,
    status TEXT DEFAULT 'open',
    pipedrive_status TEXT,
    pipedrive_last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_jobs_pipedrive_id ON jobs(pipedrive_deal_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_person_id ON jobs(person_id);

-- Verify table was created
SELECT * FROM jobs LIMIT 0;
