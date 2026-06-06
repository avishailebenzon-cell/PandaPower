-- Migration 011: Cost tracking table (llm_usage)
--
-- Single source of truth for "what does the system cost". One row per billable
-- operation, written best-effort by integrations.usage_tracker:
--   - Claude calls (stage = cv_parse / agent_match / pandi_* …), token-based.
--   - ConvertAPI conversions (stage = convertapi_extract), per-conversion cost.
-- The /admin/usage endpoints aggregate this into per-stage totals and the
-- per-unit metrics (avg cost per CV scan, avg cost per match).

CREATE TABLE IF NOT EXISTS llm_usage (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stage               TEXT NOT NULL,
    model               TEXT,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    total_tokens        INTEGER NOT NULL DEFAULT 0,
    -- For non-token costs (ConvertAPI) this holds the per-row $ directly.
    estimated_cost_usd  NUMERIC(12, 6) NOT NULL DEFAULT 0,
    -- Optional: how many billable units this row represents (e.g. ConvertAPI
    -- conversions). 1 for a single Claude call.
    units               INTEGER NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The dashboard queries by time window and groups by stage.
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_usage_stage ON llm_usage (stage);
CREATE INDEX IF NOT EXISTS idx_llm_usage_stage_created ON llm_usage (stage, created_at DESC);
