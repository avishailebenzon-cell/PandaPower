-- Phase 9: Candidate Creation from Parsed CVs
-- Run this in Supabase SQL Editor to create candidates table

-- Create candidates table
CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Basic information from CV parsing
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,

    -- Professional information
    location TEXT,
    clearance_level TEXT,
    key_skills TEXT[] DEFAULT ARRAY[]::TEXT[],
    years_of_experience INTEGER,

    -- Education information
    top_education JSONB,

    -- Experience summary
    experiences JSONB DEFAULT '[]'::JSONB,

    -- CV Linkage
    cv_file_id UUID NOT NULL REFERENCES cv_files(id) ON DELETE CASCADE,

    -- Confidence and quality metrics
    overall_confidence_score NUMERIC(3,2) CHECK (overall_confidence_score >= 0 AND overall_confidence_score <= 1),
    field_confidence_scores JSONB,

    -- Source and extraction metadata
    extracted_from_cv JSONB,
    extraction_notes TEXT,
    detected_language TEXT,

    -- Audit fields
    created_from_cv_parse BOOLEAN DEFAULT true,
    source_email_from TEXT,
    source_email_received_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS candidates_name_idx ON candidates(name);
CREATE INDEX IF NOT EXISTS candidates_email_idx ON candidates(email);
CREATE INDEX IF NOT EXISTS candidates_cv_file_id_idx ON candidates(cv_file_id);
CREATE INDEX IF NOT EXISTS candidates_location_idx ON candidates(location);
CREATE INDEX IF NOT EXISTS candidates_overall_confidence_idx ON candidates(overall_confidence_score DESC);
CREATE INDEX IF NOT EXISTS candidates_created_at_idx ON candidates(created_at DESC);
CREATE INDEX IF NOT EXISTS candidates_clearance_level_idx ON candidates(clearance_level);

-- Create a view for active candidates (not deleted)
CREATE OR REPLACE VIEW active_candidates AS
SELECT *
FROM candidates
WHERE deleted_at IS NULL;

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_candidates_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER candidates_updated_at_trigger
BEFORE UPDATE ON candidates
FOR EACH ROW
EXECUTE FUNCTION update_candidates_updated_at();

-- Verify the table was created
SELECT COUNT(*) as candidates_count FROM candidates;
