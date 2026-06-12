-- Migration 022: company-employee match flag
-- ---------------------------------------------------------------------------
-- Candidates who are CURRENT company employees (Pipedrive contact_status =
-- "עובד חברה" / "employee") must never be forwarded to Tal — it makes no sense
-- to approach a company employee about a company job. But we DO still want to
-- SEE their matches in Carmit's screens (so we can verify the matching engine
-- is working), clearly tagged.
--
-- This flag is denormalized onto the match so (a) the Carmit→Tal handoff can
-- filter on it cheaply and (b) the UI can render the "עובד חברה" tag without an
-- extra join. It is maintained by the weekly company-employee sync and by the
-- handoff guard (workers/company_employees.py).
ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS is_company_employee BOOLEAN NOT NULL DEFAULT FALSE;

-- Partial index: the gate query only ever cares about the TRUE rows (a tiny
-- fraction — only matches belonging to actual company employees).
CREATE INDEX IF NOT EXISTS idx_matches_is_company_employee
    ON matches (is_company_employee)
    WHERE is_company_employee = TRUE;
