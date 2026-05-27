-- Add organization and contact person fields to jobs table
-- Enables syncing organization and contact information from Pipedrive
-- Displayed in Carmit page and agent recruitment screens

-- Add columns to jobs table for organization and contact tracking
ALTER TABLE jobs
ADD COLUMN organization_name TEXT DEFAULT NULL,
ADD COLUMN contact_person_name TEXT DEFAULT NULL;

-- Create indexes for efficient querying and filtering
CREATE INDEX idx_jobs_organization_name ON jobs(organization_name)
WHERE organization_name IS NOT NULL;

CREATE INDEX idx_jobs_contact_person_name ON jobs(contact_person_name)
WHERE contact_person_name IS NOT NULL;

-- Add comments documenting the new fields
COMMENT ON COLUMN jobs.organization_name IS 'Name of the organization (ארגון) associated with this job. Synced from Pipedrive organizations table via org_id foreign key.';
COMMENT ON COLUMN jobs.contact_person_name IS 'Name of the contact person (איש קשר) associated with this job. Synced from Pipedrive contacts table via person_id foreign key.';
