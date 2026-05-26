-- Phase 11: Enhance Candidates Table for Scoring
-- Adds skill metrics, scoring, and readiness tracking

-- Add new columns to candidates table
ALTER TABLE candidates ADD COLUMN (
  -- Skill metrics
  normalized_skills_count INT DEFAULT 0,
  average_skill_confidence NUMERIC(3,2) DEFAULT 0,
  skill_readiness_status TEXT DEFAULT 'INCOMPLETE',  -- READY, REVIEW, INCOMPLETE

  -- Scoring
  recommendation_score INT DEFAULT 0,  -- 0-100
  last_skill_analysis_at TIMESTAMPTZ,

  -- Management
  manually_reviewed_at TIMESTAMPTZ,
  reviewed_by_user_id TEXT,
  review_notes TEXT,

  -- Tracking
  last_updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for filtering and sorting
CREATE INDEX idx_candidates_skill_readiness_status ON candidates(skill_readiness_status);
CREATE INDEX idx_candidates_recommendation_score ON candidates(recommendation_score DESC);
CREATE INDEX idx_candidates_avg_skill_confidence ON candidates(average_skill_confidence DESC);
CREATE INDEX idx_candidates_normalized_skills_count ON candidates(normalized_skills_count DESC);
CREATE INDEX idx_candidates_last_skill_analysis ON candidates(last_skill_analysis_at DESC);

-- Create view for readiness summary
CREATE OR REPLACE VIEW candidate_readiness_summary AS
SELECT
  c.id,
  c.name,
  c.detected_language,
  COUNT(DISTINCT cs.skill_id) as normalized_skills_count,
  AVG(cs.confidence_score) as average_confidence,
  c.skill_readiness_status,
  c.recommendation_score,
  c.manually_reviewed_at,
  MAX(cs.created_at) as last_skill_added_at
FROM candidates c
LEFT JOIN candidate_skills cs ON c.id = cs.candidate_id
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.name, c.detected_language, c.skill_readiness_status, c.recommendation_score, c.manually_reviewed_at;

-- Create view for scoring dashboard
CREATE OR REPLACE VIEW candidate_scoring_dashboard AS
SELECT
  c.id,
  c.name,
  c.detected_language,
  COUNT(DISTINCT cs.skill_id) as skill_count,
  AVG(cs.confidence_score) as avg_confidence,
  COUNT(DISTINCT CASE WHEN cs.confidence_score >= 0.85 THEN cs.skill_id END) as high_confidence_skills,
  COUNT(DISTINCT CASE WHEN cs.confidence_score < 0.85 THEN cs.skill_id END) as low_confidence_skills,
  COUNT(DISTINCT s.category) as skill_categories,
  c.skill_readiness_status,
  c.recommendation_score,
  c.last_skill_analysis_at
FROM candidates c
LEFT JOIN candidate_skills cs ON c.id = cs.candidate_id
LEFT JOIN skills s ON cs.skill_id = s.id
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.name, c.detected_language, c.skill_readiness_status, c.recommendation_score, c.last_skill_analysis_at
ORDER BY c.recommendation_score DESC;
