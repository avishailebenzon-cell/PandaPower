-- 017_pipedrive_delta_sync_cursor.sql
-- Adds a dedicated delta-sync cursor to pipedrive_sync_schedule.
--
-- Why: the scheduler now does incremental (delta) syncs via Pipedrive's
-- /v1/recents endpoint instead of re-fetching every person/deal/org each run
-- (which was exhausting the daily API budget -> 429 "daily request budget
-- exceeded"). We advance this cursor ONLY on a successful sync, so a transient
-- failure (e.g. a 429) does not force an expensive full re-fetch next run.
--
-- Safe & idempotent: only adds a nullable column, touches no existing data.

ALTER TABLE pipedrive_sync_schedule
    ADD COLUMN IF NOT EXISTS last_successful_sync_at timestamptz;

-- Backfill: for schedules whose last run completed cleanly, seed the cursor
-- from last_sync_at so they begin doing cheap deltas immediately instead of
-- one more full sync. Rows whose last run failed stay NULL -> the next run
-- does a single full sync to establish a clean baseline.
UPDATE pipedrive_sync_schedule
SET last_successful_sync_at = last_sync_at
WHERE last_successful_sync_at IS NULL
  AND last_sync_status = 'completed'
  AND last_sync_at IS NOT NULL;
