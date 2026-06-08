-- Migration: Test match rows for agent test conversations
-- Date: 2026-06-08
-- Description: Lets an operator inject a deliberate TEST match into the matches
-- table (for Tal / Elad) that targets a test phone number instead of a real
-- candidate/client. The row is self-contained: candidate_id / job_id stay NULL,
-- and the contact name + job details + destination phone live directly on the
-- match so no synthetic candidates/jobs rows are needed. From there the row
-- flows through the normal queue → Activate → conversation pipeline with zero
-- behavioural difference, except the WhatsApp goes to the test phone.

ALTER TABLE matches ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT FALSE;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS test_phone TEXT;
-- All the display/context fields the test screen collected:
--   {contact_name, job_title, job_description, job_qualifications,
--    job_location, job_security_clearance, organization_name, candidate_clearance}
ALTER TABLE matches ADD COLUMN IF NOT EXISTS test_meta JSONB;

CREATE INDEX IF NOT EXISTS idx_matches_is_test ON matches(is_test) WHERE is_test = TRUE;

COMMENT ON COLUMN matches.is_test IS 'TRUE for operator-created test matches (test conversations).';
COMMENT ON COLUMN matches.test_phone IS 'Destination WhatsApp number for a test match (digits only).';
COMMENT ON COLUMN matches.test_meta IS 'Self-contained display/context fields for a test match (contact name + job details).';
