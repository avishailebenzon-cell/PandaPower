-- Migration: Add Manual CV Upload System Schema
-- Date: 2026-05-23
-- Description: Add candidate_categories table and update cv_files/candidates tables for manual upload support

-- Create candidate_categories table
CREATE TABLE IF NOT EXISTS candidate_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  level INTEGER DEFAULT 1,
  skills TEXT[] DEFAULT ARRAY[]::TEXT[],
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on name for faster lookups
CREATE INDEX IF NOT EXISTS idx_candidate_categories_name ON candidate_categories(name);

-- Add category_id column to cv_files table if it doesn't exist
ALTER TABLE cv_files ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES candidate_categories(id) ON DELETE SET NULL;

-- Add upload_method column to cv_files table if it doesn't exist
-- Values: 'manual', 'email', 'api'
ALTER TABLE cv_files ADD COLUMN IF NOT EXISTS upload_method TEXT DEFAULT 'email';

-- Add batch_id column to cv_files table if it doesn't exist
-- Groups files uploaded together in a single manual-upload batch
ALTER TABLE cv_files ADD COLUMN IF NOT EXISTS batch_id UUID;
CREATE INDEX IF NOT EXISTS idx_cv_files_batch_id ON cv_files(batch_id);

-- Manual-upload-only columns not used by the email ingest pipeline
ALTER TABLE cv_files ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE cv_files ADD COLUMN IF NOT EXISTS file_extension TEXT;

-- Add category_id column to candidates table if it doesn't exist
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES candidate_categories(id) ON DELETE SET NULL;

-- Add intake_method column to candidates table if it doesn't exist
-- Values: 'manual_upload', 'email', 'api'
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS intake_method TEXT DEFAULT 'email';

-- Add intake_source column to candidates table if it doesn't exist
-- Stores the source of intake (email subject, filename, etc.)
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS intake_source TEXT;

-- Add extraction_confidence column to candidates table if it doesn't exist
-- Score from 0.0 to 1.0 indicating confidence in the extraction
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS extraction_confidence FLOAT DEFAULT 0.0;

-- Add extraction_notes column to candidates table if it doesn't exist
-- Any notes from the extraction process
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS extraction_notes TEXT;

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_cv_files_category_id ON cv_files(category_id);
CREATE INDEX IF NOT EXISTS idx_cv_files_upload_method ON cv_files(upload_method);
CREATE INDEX IF NOT EXISTS idx_candidates_category_id ON candidates(category_id);
CREATE INDEX IF NOT EXISTS idx_candidates_intake_method ON candidates(intake_method);

-- Insert default candidate categories
INSERT INTO candidate_categories (name, description, level, skills)
VALUES
  ('תוכנה', 'Software Engineers - כל הדרגות', 1, ARRAY['Python', 'Java', 'C++', 'JavaScript', 'TypeScript', 'Go', 'Rust', 'NodeJS', 'React', 'Vue', 'AWS', 'Docker', 'Kubernetes', 'SQL', 'PostgreSQL', 'MongoDB']),
  ('אלקטרוניקה', 'Electronics Engineers - תכנון מעגלים', 2, ARRAY['FPGA', 'VHDL', 'Verilog', 'PCB Design', 'RF Design', 'Analog', 'Digital', 'MATLAB', 'Cadence', 'Altium']),
  ('QA', 'Quality Assurance Engineers', 1, ARRAY['Selenium', 'Testing', 'Automation', 'LoadRunner', 'JMeter', 'API Testing', 'Python', 'Java', 'Manual Testing', 'Test Planning']),
  ('סיסטמים', 'Systems Administrators & DevOps', 2, ARRAY['Linux', 'Windows', 'Networking', 'DevOps', 'Docker', 'Kubernetes', 'AWS', 'Azure', 'GCP', 'Terraform', 'Ansible', 'Python', 'Bash']),
  ('IT', 'IT Support & Infrastructure', 1, ARRAY['Helpdesk', 'Windows', 'Network', 'Active Directory', 'IT Support', 'Infrastructure', 'Ticketing Systems', 'CompTIA']),
  ('מכני', 'Mechanical Engineers', 2, ARRAY['CAD', 'SOLIDWORKS', 'AutoCAD', 'FEA', 'Manufacturing', 'CATIA', 'NX', 'Design', 'Simulation', 'Physics']),
  ('שונות', 'General / Other Positions', 1, ARRAY['Various', 'Other', 'General'])
ON CONFLICT DO NOTHING;

-- Update existing cv_files records to have upload_method if not set
UPDATE cv_files SET upload_method = 'email' WHERE upload_method IS NULL;

-- Update existing candidates records to have intake_method if not set
UPDATE candidates SET intake_method = 'email' WHERE intake_method IS NULL;

-- Create view for upload batch status
CREATE OR REPLACE VIEW v_cv_upload_batch_status AS
SELECT
  batch_id,
  COUNT(*) as total_files,
  COUNT(*) FILTER (WHERE parse_status = 'processing' OR parse_status = 'parsing') as processing,
  COUNT(*) FILTER (WHERE parse_status = 'success') as success,
  COUNT(*) FILTER (WHERE parse_status = 'failed') as failed,
  MAX(created_at) as latest_file_time,
  MIN(created_at) as earliest_file_time
FROM cv_files
WHERE upload_method = 'manual'
GROUP BY batch_id;

-- Add comments for documentation
COMMENT ON TABLE candidate_categories IS 'Predefined candidate categories for manual CV uploads and categorization';
COMMENT ON COLUMN candidate_categories.level IS 'Experience level: 1=Junior/Entry, 2=Mid/Senior, 3=Principal/Lead';
COMMENT ON TABLE cv_files IS 'CV file records with extraction metadata';
COMMENT ON COLUMN cv_files.upload_method IS 'Source of file: manual, email, or api';
COMMENT ON TABLE candidates IS 'Candidate profiles extracted from CVs';
COMMENT ON COLUMN candidates.intake_method IS 'How candidate entered system: manual_upload, email, or api';
COMMENT ON COLUMN candidates.extraction_confidence IS 'Confidence score 0.0-1.0 of CV parsing accuracy';
