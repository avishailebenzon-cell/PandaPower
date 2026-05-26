-- Phase 8: CV Parsing Database Schema Migration
-- Run this in Supabase SQL Editor to add Phase 8 columns

-- Add missing columns to cv_files table
ALTER TABLE cv_files
ADD COLUMN IF NOT EXISTS parse_status text DEFAULT 'pending' CHECK (parse_status IN ('pending', 'parsing', 'success', 'failed')),
ADD COLUMN IF NOT EXISTS raw_text text,
ADD COLUMN IF NOT EXISTS llm_analysis jsonb,
ADD COLUMN IF NOT EXISTS parse_duration_ms integer,
ADD COLUMN IF NOT EXISTS llm_tokens_used integer,
ADD COLUMN IF NOT EXISTS detected_language text,
ADD COLUMN IF NOT EXISTS parse_error text,
ADD COLUMN IF NOT EXISTS processing_started_at timestamp with time zone,
ADD COLUMN IF NOT EXISTS processing_completed_at timestamp with time zone;

-- Create index for faster status queries
CREATE INDEX IF NOT EXISTS cv_files_parse_status_idx ON cv_files(parse_status);
CREATE INDEX IF NOT EXISTS cv_files_processing_completed_idx ON cv_files(processing_completed_at DESC);

-- Set all existing CVs from Phase 7 to pending status
UPDATE cv_files
SET parse_status = 'pending'
WHERE parse_status IS NULL;

-- Verify the migration
SELECT
  COUNT(*) as total_cvs,
  COUNT(*) FILTER (WHERE parse_status = 'pending') as pending,
  COUNT(*) FILTER (WHERE parse_status = 'parsing') as parsing,
  COUNT(*) FILTER (WHERE parse_status = 'success') as success,
  COUNT(*) FILTER (WHERE parse_status = 'failed') as failed
FROM cv_files;
