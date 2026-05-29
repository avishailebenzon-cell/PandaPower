-- Phase 34: Add referral tracking with unique referral numbers and SLA management

-- Add referral_number to candidate_referrals
ALTER TABLE candidate_referrals
ADD COLUMN referral_number TEXT,
ADD COLUMN referral_created_at TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN sla_deadline TIMESTAMPTZ,  -- 48 hours from creation
ADD COLUMN assigned_to_user_id UUID REFERENCES users(id);

-- Create sequence for referral numbers
CREATE SEQUENCE referral_number_seq START WITH 1000 INCREMENT BY 1;

-- Function to generate referral_number (REF-2026-1000, REF-2026-1001, etc)
CREATE OR REPLACE FUNCTION generate_referral_number()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.referral_number IS NULL THEN
    NEW.referral_number := 'REF-2026-' || nextval('referral_number_seq')::text;
    NEW.sla_deadline := NEW.referral_created_at + INTERVAL '48 hours';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-generate referral_number on insert
CREATE TRIGGER trg_generate_referral_number
BEFORE INSERT ON candidate_referrals
FOR EACH ROW
  EXECUTE FUNCTION generate_referral_number();

-- Create unique index on referral_number
CREATE UNIQUE INDEX idx_referrals_number ON candidate_referrals(referral_number);

-- Index for SLA tracking
CREATE INDEX idx_referrals_sla_deadline ON candidate_referrals(sla_deadline)
WHERE status IN ('client_interested', 'pending_full_cv_approval', 'in_recruitment_process');

-- Table for referral status history (for tracking SLA and transitions)
CREATE TABLE IF NOT EXISTS candidate_referral_status_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  referral_id UUID NOT NULL REFERENCES candidate_referrals(id) ON DELETE CASCADE,
  status_from TEXT,
  status_to TEXT NOT NULL,
  notes TEXT,
  changed_by_user_id UUID REFERENCES users(id),
  changed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_referral_tracking_referral ON candidate_referral_status_tracking(referral_id);
CREATE INDEX idx_referral_tracking_changed_at ON candidate_referral_status_tracking(changed_at DESC);
