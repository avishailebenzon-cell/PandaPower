-- Session 36: Scheduler reliability — persisted per-task heartbeat.
--
-- Single source of truth for "is each scheduled process actually running?".
-- The always-on in-process scheduler (apps/backend/src/pandapower/main.py)
-- upserts one row per task on every run. The /admin/system/heartbeat endpoint
-- reads this table to flag any task whose last_run_at is older than 2x its
-- expected interval (= stalled). Survives process restarts (unlike the
-- in-memory last_run dict), so a crash/stall is detectable after the fact.

CREATE TABLE IF NOT EXISTS scheduler_heartbeats (
  task_name TEXT PRIMARY KEY,
  last_run_at TIMESTAMPTZ,
  last_status TEXT,                       -- completed | skipped | failed | crashed
  last_result JSONB,
  last_error TEXT,
  consecutive_failures INT DEFAULT 0,
  expected_interval_seconds INT,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS. The backend connects with the service-role key which bypasses
-- RLS, so writes are unaffected; we add an authenticated read policy so the
-- admin dashboard can read it directly if ever needed.
ALTER TABLE scheduler_heartbeats ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated can view heartbeats" ON scheduler_heartbeats
  FOR SELECT USING (auth.role() = 'authenticated');
