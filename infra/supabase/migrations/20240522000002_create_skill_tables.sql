-- Phase 10: Create Skill Normalization Tables
-- Supports mapping raw extracted skills to canonical skill taxonomy
-- Enables multilingual skill matching (Hebrew + English)

-- Create canonical skills table
CREATE TABLE skills (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Bilingual names
  name TEXT NOT NULL UNIQUE,  -- English name (canonical)
  name_he TEXT,               -- Hebrew name

  -- Categorization (bilingual)
  category TEXT NOT NULL,     -- e.g., 'Programming Language', 'Framework', 'Tool', 'Soft Skill', 'Security Clearance'
  category_he TEXT,

  -- Documentation
  description TEXT,           -- Detailed description/context

  -- Aliases for better matching
  aliases TEXT[] DEFAULT ARRAY[]::TEXT[],  -- e.g., ["JS", "JavaScript ES6"] for JavaScript
  aliases_he TEXT[],                        -- Hebrew aliases

  -- Metadata
  popularity_score NUMERIC(3,2) DEFAULT 0.5,  -- 0-1 scale, higher = more commonly used
  is_active BOOLEAN DEFAULT true,

  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Constraints
  CONSTRAINT valid_popularity CHECK (popularity_score >= 0 AND popularity_score <= 1)
);

-- Create indexes for skills
CREATE INDEX idx_skills_name ON skills(name);
CREATE INDEX idx_skills_name_he ON skills(name_he);
CREATE INDEX idx_skills_category ON skills(category);
CREATE INDEX idx_skills_category_he ON skills(category_he);
CREATE INDEX idx_skills_popularity ON skills(popularity_score DESC);
CREATE INDEX idx_skills_is_active ON skills(is_active);

-- Create skill mappings table (tracks raw → canonical mappings)
CREATE TABLE skill_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Raw vs canonical mapping
  raw_skill_text TEXT NOT NULL,             -- As extracted from CV
  skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,

  -- Metadata
  source_language TEXT,                     -- Language of raw skill ('he', 'en', etc.)
  mapping_method TEXT,                      -- How it was mapped: 'claude_ai', 'similarity_matching', 'manual'
  confidence_score NUMERIC(3,2),            -- 0-1, quality of the mapping
  times_used INT DEFAULT 1,                 -- How many candidates use this mapping

  is_active BOOLEAN DEFAULT true,

  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  -- Uniqueness: same raw skill can map to same canonical skill in same language only once
  UNIQUE(raw_skill_text, skill_id, source_language)
);

-- Create indexes for skill_mappings
CREATE INDEX idx_skill_mappings_raw_text ON skill_mappings(raw_skill_text);
CREATE INDEX idx_skill_mappings_skill_id ON skill_mappings(skill_id);
CREATE INDEX idx_skill_mappings_language ON skill_mappings(source_language);
CREATE INDEX idx_skill_mappings_method ON skill_mappings(mapping_method);
CREATE INDEX idx_skill_mappings_times_used ON skill_mappings(times_used DESC);
CREATE INDEX idx_skill_mappings_confidence ON skill_mappings(confidence_score DESC);
CREATE INDEX idx_skill_mappings_active ON skill_mappings(is_active);

-- Update candidate_skills table to add missing columns
-- We keep both skill_id (FK) and denormalized skill_name/category for performance
ALTER TABLE candidate_skills
ADD COLUMN skill_id UUID REFERENCES skills(id) ON DELETE SET NULL,
ADD COLUMN normalization_method TEXT;

-- Create detailed view for candidate skills (join with skills table)
CREATE OR REPLACE VIEW candidate_skills_detailed AS
SELECT
  cs.id,
  cs.candidate_id,
  c.name AS candidate_name,
  c.detected_language,
  s.id AS skill_id,
  s.name AS skill_name,
  s.name_he AS skill_name_he,
  s.category AS skill_category,
  s.category_he AS skill_category_he,
  cs.raw_skill_text,
  cs.confidence_score,
  cs.proficiency_level,
  cs.years_in_skill,
  cs.normalization_method,
  cs.created_at
FROM candidate_skills cs
JOIN candidates c ON cs.candidate_id = c.id
LEFT JOIN skills s ON cs.skill_id = s.id
WHERE c.deleted_at IS NULL;
