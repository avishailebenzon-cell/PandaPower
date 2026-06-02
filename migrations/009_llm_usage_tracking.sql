-- LLM token-usage tracking (per-stage Anthropic consumption dashboard)
-- Records one row per Claude API call so the admin can see exactly where
-- Anthropic credits are spent (cv_parse / agent_match / pandi_conversation / ...).
--
-- Apply via the Supabase SQL editor, or POST /admin/setup/migrations.

CREATE TABLE IF NOT EXISTS llm_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stage TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT DEFAULT 0,
    output_tokens INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    estimated_cost_usd NUMERIC(12,6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_stage ON llm_usage(stage);
CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage(model);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at DESC);
