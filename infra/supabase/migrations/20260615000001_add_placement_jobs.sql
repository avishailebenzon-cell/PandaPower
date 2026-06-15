-- Placement jobs ("משרות השמה"): jobs ingested directly from recruitment-agency
-- emails (e.g. @adamtotal.co.il). The candidate becomes the CLIENT's employee,
-- not a PandaTech employee, so these jobs are NOT synced to Pipedrive — they
-- live only inside our system and are flagged with is_placement=true.
--
-- This reuses the shared `jobs` table so all existing machinery (Carmit
-- routing, agent matching, recruiter screens, PipedriveDataTable) works for
-- placement jobs for free.

-- Pipedrive deal id must become nullable: placement jobs have no Pipedrive deal.
ALTER TABLE jobs ALTER COLUMN pipedrive_deal_id DROP NOT NULL;

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'pipedrive',
  ADD COLUMN IF NOT EXISTS is_placement BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS placement_source_email TEXT,        -- sender address (e.g. mailer@adamtotal.co.il)
  ADD COLUMN IF NOT EXISTS placement_contact_name TEXT,        -- agency contact pulled from the body
  ADD COLUMN IF NOT EXISTS placement_contact_phone TEXT,       -- agency contact phone pulled from the body
  ADD COLUMN IF NOT EXISTS placement_outlook_message_id TEXT,  -- dedup: one job per source email
  ADD COLUMN IF NOT EXISTS placement_external_ref TEXT,        -- agency's job id (e.g. 76047697) — dedup across re-forwards
  ADD COLUMN IF NOT EXISTS job_number TEXT;                    -- internal id (PL-####) used in place of a deal id

-- Each source email yields exactly one placement job (idempotent re-scan).
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_placement_msg
  ON jobs (placement_outlook_message_id)
  WHERE placement_outlook_message_id IS NOT NULL;

-- Preserve uniqueness of pipedrive_deal_id only when it is present (the old
-- column-level UNIQUE NOT NULL would otherwise reject multiple NULL deal ids on
-- some engines / future tightening).
-- The original uniqueness on pipedrive_deal_id is a table CONSTRAINT, not a
-- bare index, so it must be dropped as a constraint.
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_pipedrive_deal_id_key;
DROP INDEX IF EXISTS jobs_pipedrive_deal_id_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_deal_id
  ON jobs (pipedrive_deal_id)
  WHERE pipedrive_deal_id IS NOT NULL;

-- Fast "placement jobs only" filtering for the UI.
CREATE INDEX IF NOT EXISTS idx_jobs_is_placement
  ON jobs (is_placement)
  WHERE is_placement = TRUE;
