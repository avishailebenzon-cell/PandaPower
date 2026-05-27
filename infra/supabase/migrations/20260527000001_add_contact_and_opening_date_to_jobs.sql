-- Add contact person name and job opening date fields to jobs table
-- Enables displaying contact info and opening date in Carmit dashboard

-- Add columns to jobs table
ALTER TABLE jobs
ADD COLUMN contact_person_name TEXT DEFAULT NULL,
ADD COLUMN job_opening_date TIMESTAMPTZ DEFAULT NULL;

-- Create indexes for filtering and sorting
CREATE INDEX idx_jobs_contact_person_name ON jobs(contact_person_name)
WHERE contact_person_name IS NOT NULL;

CREATE INDEX idx_jobs_opening_date ON jobs(job_opening_date DESC)
WHERE job_opening_date IS NOT NULL;

-- Add comments documenting the new fields
COMMENT ON COLUMN jobs.contact_person_name IS 'Name of the contact person at the client organization. Extracted from Pipedrive person data linked to the deal.';
COMMENT ON COLUMN jobs.job_opening_date IS 'Date when the job was created/opened. Extracted from Pipedrive deal add_time field. Represents when the recruitment need was identified.';
