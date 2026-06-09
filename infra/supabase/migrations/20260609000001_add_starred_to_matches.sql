-- Add favorite/starred flag to matches.
-- A match can be starred at any stage (Carmit, Tal, Elad). Orthogonal to the
-- match state machine; surfaced as an orange star + "favorites only" filter
-- in every agent queue.

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS is_starred BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS starred_at TIMESTAMPTZ;

-- Partial index — only starred rows, keeps the "favorites only" filter fast.
CREATE INDEX IF NOT EXISTS idx_matches_is_starred
    ON matches(is_starred) WHERE is_starred = TRUE;
