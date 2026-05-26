-- Phase 10: Add candidate_number system
-- Public identifier for candidates (anonymization layer)
-- Used exclusively in external-facing APIs (Pandi, client reports)

-- Add column to candidates table
ALTER TABLE candidates ADD COLUMN candidate_number TEXT;

-- Create sequence for auto-generation
CREATE SEQUENCE candidate_number_seq START WITH 1 INCREMENT BY 1;

-- Function to generate candidate_number on insert
CREATE OR REPLACE FUNCTION generate_candidate_number()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.candidate_number IS NULL THEN
    NEW.candidate_number := 'C' || LPAD(nextval('candidate_number_seq')::text, 6, '0');
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-generate on insert
CREATE TRIGGER trg_generate_candidate_number
  BEFORE INSERT ON candidates
  FOR EACH ROW
  EXECUTE FUNCTION generate_candidate_number();

-- Backfill existing candidates
UPDATE candidates
SET candidate_number = 'C' || LPAD(ROW_NUMBER() OVER (ORDER BY created_at, id)::text, 6, '0')
WHERE candidate_number IS NULL;

-- Make column NOT NULL and add uniqueness constraint
ALTER TABLE candidates
ALTER COLUMN candidate_number SET NOT NULL;

CREATE UNIQUE INDEX idx_candidates_candidate_number ON candidates(candidate_number);

-- Index for quick lookups by external identifier
CREATE INDEX idx_candidates_number_lookup ON candidates(candidate_number);
