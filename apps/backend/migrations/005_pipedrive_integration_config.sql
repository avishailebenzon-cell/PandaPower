-- Migration: Add Pipedrive Integration Configuration Schema
-- Date: 2026-05-23
-- Description: Add tables for managing Pipedrive sync configuration, field mappings, and sync schedules

-- Table for Pipedrive API configuration
CREATE TABLE IF NOT EXISTS pipedrive_config (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  api_token TEXT NOT NULL,
  api_domain TEXT NOT NULL DEFAULT 'https://api.pipedrive.com',
  bot_user_id TEXT,
  is_active BOOLEAN DEFAULT false,
  last_validated_at TIMESTAMP WITH TIME ZONE,
  validation_error TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for Pipedrive field mappings (custom fields)
CREATE TABLE IF NOT EXISTS pipedrive_field_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL, -- 'deal', 'person', 'organization'
  pandapower_field TEXT NOT NULL, -- e.g., 'job_title', 'contact_type'
  pipedrive_field_id TEXT NOT NULL, -- numeric ID of custom field in Pipedrive
  pipedrive_field_name TEXT NOT NULL, -- display name
  field_type TEXT, -- 'text', 'number', 'select', 'date', etc.
  is_required BOOLEAN DEFAULT false,
  custom_field_mapping JSONB, -- for select fields: {value: display_value, ...}
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(entity_type, pandapower_field)
);

-- Table for sync schedules per entity type
CREATE TABLE IF NOT EXISTS pipedrive_sync_schedule (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL UNIQUE, -- 'persons', 'organizations', 'deals'
  sync_direction TEXT NOT NULL DEFAULT 'bidirectional', -- 'inbound', 'outbound', 'bidirectional'
  sync_interval_minutes INTEGER NOT NULL DEFAULT 60, -- how often to sync
  sync_enabled BOOLEAN DEFAULT true,
  filter_by_contact_type TEXT, -- for persons: 'all', 'client', 'potential_client', 'candidate', 'employee'
  filter_by_status TEXT, -- optional status filter
  last_sync_at TIMESTAMP WITH TIME ZONE,
  last_sync_status TEXT, -- 'success', 'failed', 'in_progress'
  last_sync_error TEXT,
  next_scheduled_sync TIMESTAMP WITH TIME ZONE,
  sync_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for sync history and logging
CREATE TABLE IF NOT EXISTS pipedrive_sync_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL,
  sync_direction TEXT NOT NULL, -- 'inbound' or 'outbound'
  total_records INTEGER DEFAULT 0,
  created_count INTEGER DEFAULT 0,
  updated_count INTEGER DEFAULT 0,
  failed_count INTEGER DEFAULT 0,
  status TEXT NOT NULL, -- 'success', 'failed', 'partial'
  error_message TEXT,
  duration_ms INTEGER,
  details JSONB, -- detailed error logs per record
  started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE
);

-- Table for field mapping validation cache
CREATE TABLE IF NOT EXISTS pipedrive_field_validation (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pipedrive_field_id TEXT NOT NULL,
  field_label TEXT,
  field_type TEXT,
  valid_options JSONB, -- for select/dropdown fields
  is_custom_field BOOLEAN DEFAULT true,
  last_checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(pipedrive_field_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_pipedrive_field_mappings_entity ON pipedrive_field_mappings(entity_type);
CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_schedule_entity ON pipedrive_sync_schedule(entity_type);
CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_entity_date ON pipedrive_sync_log(entity_type, started_at DESC);

-- Insert default sync schedules
INSERT INTO pipedrive_sync_schedule (entity_type, sync_direction, sync_interval_minutes, sync_enabled)
VALUES
  ('persons', 'bidirectional', 60, true),
  ('organizations', 'bidirectional', 60, true),
  ('deals', 'bidirectional', 30, true)
ON CONFLICT (entity_type) DO NOTHING;

-- Add comments for documentation
COMMENT ON TABLE pipedrive_config IS 'Pipedrive API configuration and authentication details';
COMMENT ON TABLE pipedrive_field_mappings IS 'Mapping of PandaPower fields to Pipedrive custom field IDs';
COMMENT ON TABLE pipedrive_sync_schedule IS 'Sync scheduling configuration for each Pipedrive entity type';
COMMENT ON TABLE pipedrive_sync_log IS 'Historical log of all sync operations for audit trail';
COMMENT ON COLUMN pipedrive_field_mappings.custom_field_mapping IS 'Maps Pipedrive select option values to display text (e.g. {"1": "Priority 1", "2": "Priority 2"})';
COMMENT ON COLUMN pipedrive_sync_schedule.filter_by_contact_type IS 'For persons: filter by contact type status - "client", "potential_client", "candidate", "employee"';
