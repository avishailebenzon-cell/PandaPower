-- Add Pipedrive sync fields to organizations table
ALTER TABLE public.organizations
    ADD COLUMN IF NOT EXISTS pipedrive_org_id BIGINT UNIQUE,
    ADD COLUMN IF NOT EXISTS org_type TEXT,
    ADD COLUMN IF NOT EXISTS classification_level INT,
    ADD COLUMN IF NOT EXISTS pipedrive_last_synced_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_organizations_pipedrive_id
    ON public.organizations(pipedrive_org_id);
