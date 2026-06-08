-- Recreate Pandi tables that never made it into production.
--
-- Diagnosis (2026-06-08): pandi_clients, pandi_conversations and
-- candidate_referrals exist in prod, but pandi_messages, pandi_message_quotas
-- and candidate_referral_history were never applied — so Pandi could not save
-- or load any WhatsApp message and never replied. The original definitions
-- live in 20240524000002_create_pandi_tables.sql; this migration recreates the
-- missing subset idempotently (IF NOT EXISTS) so it is safe to re-run.

-- pandi_messages: every inbound/outbound WhatsApp message for Pandi.
CREATE TABLE IF NOT EXISTS pandi_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES pandi_conversations(id) ON DELETE CASCADE,
  pandi_client_id UUID NOT NULL REFERENCES pandi_clients(id) ON DELETE CASCADE,
  direction TEXT NOT NULL,              -- 'inbound' | 'outbound'
  message_type TEXT DEFAULT 'text',     -- 'text' | 'document' | 'image' | 'system'
  green_api_message_id TEXT UNIQUE,     -- For deduplication
  text TEXT,
  document_url TEXT,
  document_filename TEXT,
  llm_invoked BOOLEAN DEFAULT FALSE,
  llm_model TEXT,
  llm_input_tokens INT,
  llm_output_tokens INT,
  llm_tools_called JSONB,
  was_quota_blocked BOOLEAN DEFAULT FALSE,
  inappropriate_flag BOOLEAN DEFAULT FALSE,
  flag_reason TEXT,
  sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pandi_messages_conv ON pandi_messages(conversation_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_pandi_messages_client ON pandi_messages(pandi_client_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_pandi_messages_green_api ON pandi_messages(green_api_message_id);

-- pandi_message_quotas: monthly message limits per client.
CREATE TABLE IF NOT EXISTS pandi_message_quotas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pandi_client_id UUID NOT NULL REFERENCES pandi_clients(id) ON DELETE CASCADE,
  month DATE NOT NULL,
  monthly_limit INT NOT NULL DEFAULT 100,
  messages_used INT DEFAULT 0,
  increase_requested_at TIMESTAMPTZ,
  increase_requested_amount INT,
  increase_approved_at TIMESTAMPTZ,
  -- NB: no FK to users(id) — that table does not exist in prod and the FK was
  -- the original reason this migration silently failed to apply. Plain UUID.
  increase_approved_by_user_id UUID,
  increase_approved_amount INT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(pandi_client_id, month)
);

CREATE INDEX IF NOT EXISTS idx_quota_client_month ON pandi_message_quotas(pandi_client_id, month DESC);
CREATE INDEX IF NOT EXISTS idx_quota_increase_pending ON pandi_message_quotas(increase_requested_at)
  WHERE increase_requested_at IS NOT NULL AND increase_approved_at IS NULL;

-- candidate_referral_history: audit trail of referral status changes.
CREATE TABLE IF NOT EXISTS candidate_referral_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  referral_id UUID NOT NULL REFERENCES candidate_referrals(id) ON DELETE CASCADE,
  from_status TEXT,
  to_status TEXT NOT NULL,
  triggered_by_user_id UUID,
  triggered_by_pandi_client_id UUID REFERENCES pandi_clients(id),
  reasoning TEXT,
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_history_referral
  ON candidate_referral_history(referral_id, created_at DESC);
