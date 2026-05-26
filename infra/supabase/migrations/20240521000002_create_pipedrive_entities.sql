-- Create organizations table
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipedrive_org_id BIGINT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  org_type TEXT,
  classification_level INT,
  pipedrive_last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_organizations_pipedrive_id ON organizations(pipedrive_org_id);

-- Create contacts table
CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipedrive_person_id BIGINT UNIQUE NOT NULL,
  full_name TEXT,
  email TEXT,
  phone TEXT,
  organization_id UUID REFERENCES organizations(id),
  contact_status TEXT,
  professional_domain TEXT,
  security_clearance_level TEXT,
  pipedrive_last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_contacts_pipedrive_id ON contacts(pipedrive_person_id);
CREATE INDEX idx_contacts_status ON contacts(contact_status);
CREATE INDEX idx_contacts_domain ON contacts(professional_domain);
CREATE INDEX idx_contacts_organization ON contacts(organization_id);

-- Create jobs table
CREATE TABLE jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipedrive_deal_id BIGINT UNIQUE NOT NULL,
  pipedrive_pipeline_id BIGINT,
  pipedrive_stage_id BIGINT,

  -- Custom fields
  title TEXT NOT NULL,
  description TEXT,
  qualifications TEXT,
  location TEXT,
  required_security_clearance TEXT,
  deadline DATE,
  priority INT,
  classification_level INT,

  -- Internal
  client_org_id UUID REFERENCES organizations(id),
  client_contact_id UUID REFERENCES contacts(id),
  required_domain TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  assigned_agent_code TEXT,
  assigned_agent_override BOOLEAN DEFAULT FALSE,
  override_user_id UUID,
  carmit_routing_reasoning TEXT,

  -- Meta
  pipedrive_last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jobs_pipedrive_id ON jobs(pipedrive_deal_id);
CREATE INDEX idx_jobs_active ON jobs(is_active);
CREATE INDEX idx_jobs_agent ON jobs(assigned_agent_code);
CREATE INDEX idx_jobs_classification ON jobs(classification_level);
CREATE INDEX idx_jobs_priority ON jobs(priority);
CREATE INDEX idx_jobs_client_org ON jobs(client_org_id);
