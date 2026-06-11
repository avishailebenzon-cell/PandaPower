-- 021_pandius_cv_linkage.sql
-- Close the data-linkage gap in the Pandius (פנדיוס) candidate-intake flow.
--
-- When a job seeker sends a CV over WhatsApp, the cv_files row is stored with
-- only the PHONE (candidate_email = phone), because the real email isn't known
-- yet. Separately, Pandius's save_candidate creates a contacts row with the
-- REAL email and links it to the pandius_clients row. The candidate-creation
-- worker then turns the parsed CV into a candidates row keyed off the CV's
-- extracted email/phone. Result: the parsed-CV candidate and the Pandius
-- contact could end up as two disconnected records.
--
-- This migration adds the two columns needed to bridge them reliably:
--   1. cv_files.pandius_client_id  — stamped at WhatsApp ingest (the only
--      stable handle we have at CV time), so the candidate-creation worker can
--      walk CV -> pandius_client -> contact regardless of email/phone parsing.
--   2. candidates.contact_id       — the direct, queryable candidate<->contact
--      link, stamped from both orderings (CV-then-details and details-then-CV).
--
-- Both columns are nullable and back-compatible: the email-intake CV path
-- (which already has a real email) is untouched and simply leaves them NULL.
--
-- Safe to run more than once (IF NOT EXISTS).

-- ---------------------------------------------------------------------------
-- 1) cv_files.pandius_client_id  — bridge from a WhatsApp CV to its intake row
-- ---------------------------------------------------------------------------
ALTER TABLE cv_files
    ADD COLUMN IF NOT EXISTS pandius_client_id UUID;

CREATE INDEX IF NOT EXISTS idx_cv_files_pandius_client
    ON cv_files (pandius_client_id);

-- ---------------------------------------------------------------------------
-- 2) candidates.contact_id  — direct link to the Pandius (or any) contact
-- ---------------------------------------------------------------------------
ALTER TABLE candidates
    ADD COLUMN IF NOT EXISTS contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_candidates_contact
    ON candidates (contact_id);
