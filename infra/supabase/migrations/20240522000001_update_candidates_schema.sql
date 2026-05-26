-- Phase 9: Update candidates table schema to match CandidateCreationWorker
-- This migration corrects the schema mismatch between old migration and Phase 8/9 requirements
-- Old schema: full_name_he/en, city, country, primary_domain, etc.
-- New schema: name, email, phone, location, clearance_level, key_skills, overall_confidence_score, etc.

-- Drop old candidate_skills table (if it exists)
DROP TABLE IF EXISTS candidate_skills CASCADE;

-- Drop old candidates table
DROP TABLE IF EXISTS candidates CASCADE;

-- Create new candidates table matching CandidateCreationWorker expectations
CREATE TABLE candidates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Core candidate information
  name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  location TEXT,
  detected_language TEXT DEFAULT 'en',

  -- Security clearance and experience
  clearance_level TEXT,
  years_of_experience INT,

  -- Skills and education
  key_skills TEXT[] DEFAULT ARRAY[]::TEXT[],
  top_education JSONB,
  experiences JSONB DEFAULT '[]'::jsonb,

  -- CV linkage (each candidate comes from exactly one parsed CV)
  cv_file_id UUID NOT NULL UNIQUE REFERENCES cv_files(id) ON DELETE CASCADE,

  -- Confidence metrics (from Claude API parsing)
  overall_confidence_score NUMERIC(3,2) DEFAULT 0,
  field_confidence_scores JSONB DEFAULT '{}'::jsonb,

  -- Full extraction data (preserves entire Claude analysis for auditability)
  extracted_from_cv JSONB,
  extraction_notes TEXT,

  -- Audit trail
  source_email_from TEXT,
  source_email_received_at TIMESTAMPTZ,
  created_from_cv_parse BOOLEAN DEFAULT true,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,

  -- Constraints
  CONSTRAINT valid_confidence CHECK (overall_confidence_score >= 0 AND overall_confidence_score <= 1)
);

-- Indexes for query performance
CREATE INDEX idx_candidates_name ON candidates(name);
CREATE INDEX idx_candidates_email ON candidates(LOWER(email));
CREATE INDEX idx_candidates_cv_file_id ON candidates(cv_file_id);
CREATE INDEX idx_candidates_location ON candidates(location);
CREATE INDEX idx_candidates_created_at ON candidates(created_at DESC);
CREATE INDEX idx_candidates_deleted_at ON candidates(deleted_at);
CREATE INDEX idx_candidates_clearance ON candidates(clearance_level);
CREATE INDEX idx_candidates_confidence ON candidates(overall_confidence_score DESC);
CREATE INDEX idx_candidates_lang ON candidates(detected_language);

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_candidates_updated_at
BEFORE UPDATE ON candidates
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Create candidate_skills table for Phase 10 skill normalization
CREATE TABLE candidate_skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,

  -- Raw vs canonical skill mapping
  raw_skill_text TEXT NOT NULL,
  skill_name TEXT,  -- Will be populated in Phase 10 with canonical skill name
  skill_category TEXT,  -- From canonical skills taxonomy

  -- Quality metrics
  confidence_score NUMERIC(3,2),
  proficiency_level TEXT,  -- 'beginner', 'intermediate', 'expert'
  years_in_skill NUMERIC(4,1),

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Uniqueness constraint
  UNIQUE(candidate_id, raw_skill_text)
);

-- Indexes for candidate_skills
CREATE INDEX idx_candidate_skills_candidate_id ON candidate_skills(candidate_id);
CREATE INDEX idx_candidate_skills_skill_name ON candidate_skills(skill_name);
CREATE INDEX idx_candidate_skills_raw_text ON candidate_skills(raw_skill_text);

-- Create trigger for candidate_skills updated_at
CREATE TRIGGER update_candidate_skills_updated_at
BEFORE UPDATE ON candidate_skills
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Create view for active candidates (soft delete pattern)
CREATE OR REPLACE VIEW active_candidates AS
SELECT * FROM candidates
WHERE deleted_at IS NULL;

-- Grant appropriate permissions (if using Supabase with RLS)
-- This is handled by Supabase's default policies, but can be customized
