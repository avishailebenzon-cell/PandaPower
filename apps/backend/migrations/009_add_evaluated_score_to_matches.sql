-- Migration 009: Add evaluated_score and is_passing to matches table
-- Tracks all candidate evaluations (pass & fail), not just matches

ALTER TABLE matches
ADD COLUMN is_passing BOOLEAN DEFAULT false,
ADD COLUMN evaluated_score_raw INTEGER CHECK (evaluated_score_raw >= 0 AND evaluated_score_raw <= 100);

-- Populate is_passing based on existing match_score (score >= 0.7 = pass)
UPDATE matches
SET is_passing = true
WHERE match_score >= 0.7;

-- Populate evaluated_score_raw from normalized match_score
UPDATE matches
SET evaluated_score_raw = ROUND(match_score * 100)::INTEGER
WHERE evaluated_score_raw IS NULL;

-- Create indexes for efficient querying
CREATE INDEX idx_matches_is_passing ON matches(is_passing);
CREATE INDEX idx_matches_evaluated_score ON matches(evaluated_score_raw DESC);
CREATE INDEX idx_matches_job_passing ON matches(job_id, is_passing);
CREATE INDEX idx_matches_job_score ON matches(job_id, evaluated_score_raw DESC);
