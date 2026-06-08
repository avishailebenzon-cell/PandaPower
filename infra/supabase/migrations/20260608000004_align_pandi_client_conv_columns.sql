-- Align prod pandi_clients / pandi_conversations with the columns the Pandi
-- runtime actually writes. The deployed tables were created from an older,
-- narrower definition and were missing columns the message handler / engine
-- depend on (first_message_at, whatsapp_chat_id, pandi_client_id, ...), which
-- crashed every inbound message before any reply could be produced.
-- Idempotent: ADD COLUMN IF NOT EXISTS, safe to re-run.

ALTER TABLE pandi_clients
  ADD COLUMN IF NOT EXISTS whatsapp_chat_id      TEXT,
  ADD COLUMN IF NOT EXISTS identification_method TEXT,
  ADD COLUMN IF NOT EXISTS first_message_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_message_at       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS identified_at         TIMESTAMPTZ;

ALTER TABLE pandi_conversations
  ADD COLUMN IF NOT EXISTS pandi_client_id   UUID REFERENCES pandi_clients(id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS started_at        TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS last_activity_at  TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS job_context       JSONB,
  ADD COLUMN IF NOT EXISTS summary           TEXT;

CREATE INDEX IF NOT EXISTS idx_pandi_conv_client ON pandi_conversations(pandi_client_id);
