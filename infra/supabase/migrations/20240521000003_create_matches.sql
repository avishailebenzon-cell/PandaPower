-- Create matches table
CREATE TABLE matches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
  job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,

  -- Score and reasoning
  match_score NUMERIC(5,2),
  match_reasoning TEXT,
  matched_by_agent_code TEXT,

  -- State machine
  current_state TEXT NOT NULL DEFAULT 'found',
  state_updated_at TIMESTAMPTZ DEFAULT NOW(),
  state_updated_by_agent TEXT,

  -- Carmit review
  carmit_review_notes TEXT,
  carmit_blocked_reason TEXT,

  -- Tal conversation
  tal_conversation_id UUID,
  tal_summary TEXT,
  tal_decision_reason TEXT,

  -- Elad
  elad_sent_to_client_id UUID REFERENCES contacts(id),
  elad_sent_at TIMESTAMPTZ,

  -- Pipedrive sync
  pipedrive_note_id BIGINT,

  -- Meta
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(candidate_id, job_id)
);

CREATE INDEX idx_matches_state ON matches(current_state);
CREATE INDEX idx_matches_job ON matches(job_id);
CREATE INDEX idx_matches_candidate ON matches(candidate_id);
CREATE INDEX idx_matches_score ON matches(match_score DESC);
CREATE INDEX idx_matches_created ON matches(created_at DESC);

-- Create match_state_history table
CREATE TABLE match_state_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id UUID REFERENCES matches(id) ON DELETE CASCADE,
  from_state TEXT,
  to_state TEXT NOT NULL,
  triggered_by_agent TEXT,
  triggered_by_user_id UUID,
  reasoning TEXT NOT NULL,
  is_user_override BOOLEAN DEFAULT FALSE,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_match_history_match ON match_state_history(match_id, created_at);
CREATE INDEX idx_match_history_created ON match_state_history(created_at DESC);
