-- Create candidate_referrals table for Phase 34 referral tracking
-- This table tracks referrals of candidates to clients via Pandi bot

CREATE TABLE IF NOT EXISTS candidate_referrals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Reference to candidate
  candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
  candidate_number TEXT NOT NULL,  -- e.g., "C000123" for anonymization

  -- Reference to client (Pandi)
  pandi_client_id UUID REFERENCES pandi_clients(id) ON DELETE SET NULL,

  -- Referral tracking
  referral_number TEXT UNIQUE,  -- e.g., "REF-2026-1000" (auto-generated)
  status TEXT NOT NULL DEFAULT 'presented',  -- presented, client_interested, in_recruitment_process, hired, rejected_by_us, client_declined

  -- Job context & matching
  job_context JSONB,  -- { "title": "...", "required_skills": [...], ... }
  presented_payload JSONB,  -- LLM response with candidate info & match reasoning
  llm_match_reasoning TEXT,  -- Why this candidate matches

  -- SLA tracking
  sla_deadline TIMESTAMPTZ,  -- Calculated as created_at + 48 hours (from settings)

  -- Timeline
  presented_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  status_updated_at TIMESTAMPTZ DEFAULT NOW(),
  status_notes TEXT,

  -- Audit
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_candidate_referrals_candidate_id ON candidate_referrals(candidate_id);
CREATE INDEX idx_candidate_referrals_pandi_client_id ON candidate_referrals(pandi_client_id);
CREATE INDEX idx_candidate_referrals_status ON candidate_referrals(status);
CREATE INDEX idx_candidate_referrals_sla_deadline ON candidate_referrals(sla_deadline) WHERE status IN ('presented', 'client_interested', 'in_recruitment_process');
CREATE UNIQUE INDEX idx_candidate_referrals_number ON candidate_referrals(referral_number) WHERE referral_number IS NOT NULL;

-- Create sequence for referral numbers
CREATE SEQUENCE IF NOT EXISTS referral_number_seq START WITH 1000 INCREMENT BY 1;

-- Function to generate referral_number on insert
CREATE OR REPLACE FUNCTION generate_candidate_referral_number()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.referral_number IS NULL THEN
    NEW.referral_number := 'REF-2026-' || nextval('referral_number_seq')::text;
    NEW.sla_deadline := NEW.created_at + INTERVAL '48 hours';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS trg_generate_candidate_referral_number ON candidate_referrals;
CREATE TRIGGER trg_generate_candidate_referral_number
BEFORE INSERT ON candidate_referrals
FOR EACH ROW
EXECUTE FUNCTION generate_candidate_referral_number();

-- Status tracking table for audit trail
CREATE TABLE IF NOT EXISTS candidate_referral_status_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  referral_id UUID NOT NULL REFERENCES candidate_referrals(id) ON DELETE CASCADE,
  status_from TEXT,
  status_to TEXT NOT NULL,
  notes TEXT,
  changed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_referral_status_tracking_referral_id ON candidate_referral_status_tracking(referral_id);
CREATE INDEX idx_referral_status_tracking_changed_at ON candidate_referral_status_tracking(changed_at DESC);

-- RLS Policy
ALTER TABLE candidate_referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidate_referral_status_tracking ENABLE ROW LEVEL SECURITY;

-- Allow public read (for now)
CREATE POLICY "Allow read candidate_referrals" ON candidate_referrals FOR SELECT USING (true);
CREATE POLICY "Allow write candidate_referrals" ON candidate_referrals FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow update candidate_referrals" ON candidate_referrals FOR UPDATE USING (true);
CREATE POLICY "Allow read referral_status" ON candidate_referral_status_tracking FOR SELECT USING (true);
CREATE POLICY "Allow write referral_status" ON candidate_referral_status_tracking FOR INSERT WITH CHECK (true);
