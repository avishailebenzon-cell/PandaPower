-- Pandius (פנדיוס) bot tables — the inbound, candidate-facing WhatsApp agent.
--
-- Pandius is the male counterpart to Pandi: where Pandi fields CLIENT requests
-- (looking for candidates), Pandius fields CANDIDATE requests (job seekers).
-- He collects the candidate's basic details, stores them as a contact with
-- status "מועמד לחברה" (candidate), accepts a CV (fed into the normal CV scan
-- pipeline via cv_files), and tries to surface a relevant open job.
--
-- Schema mirrors the Pandi tables (pandi_clients / pandi_conversations /
-- pandi_messages) so the shared WhatsApp-style chat screen works identically.

-- pandius_clients: one row per job-seeker who messages Pandius
CREATE TABLE IF NOT EXISTS pandius_clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Link to contacts. NULL until Pandius has collected enough details to create
  -- the contact (status = candidate). Unlike Pandi, the contact is created
  -- during the conversation, not before.
  contact_id UUID REFERENCES contacts(id) ON DELETE SET NULL,
  -- WhatsApp identification
  phone TEXT NOT NULL UNIQUE,            -- E.164 format (+972...)
  whatsapp_chat_id TEXT,                 -- Green API chat_id (typically phone@c.us)
  -- Identification tracking
  identified_at TIMESTAMPTZ,
  identification_method TEXT,            -- 'auto_phone_match' | 'manual_intake_via_bot'
  -- Interaction state
  is_active BOOLEAN DEFAULT TRUE,
  first_message_at TIMESTAMPTZ,
  last_message_at TIMESTAMPTZ,
  -- Intake flow
  intake_status TEXT DEFAULT 'not_started',
  -- 'not_started' | 'in_progress' | 'completed'
  intake_collected_data JSONB,           -- {first_name, last_name, email}
  -- Did the candidate submit a CV that was fed into the scan pipeline?
  cv_received_at TIMESTAMPTZ,
  cv_file_id UUID,                       -- latest cv_files row created from WhatsApp
  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pandius_clients_phone ON pandius_clients(phone);
CREATE INDEX IF NOT EXISTS idx_pandius_clients_contact ON pandius_clients(contact_id);
CREATE INDEX IF NOT EXISTS idx_pandius_clients_active ON pandius_clients(is_active);

-- pandius_conversations: chat sessions between a candidate and Pandius
CREATE TABLE IF NOT EXISTS pandius_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pandius_client_id UUID NOT NULL REFERENCES pandius_clients(id) ON DELETE CASCADE,
  -- Conversation state
  status TEXT NOT NULL DEFAULT 'open',
  -- 'open' | 'collecting_details' | 'awaiting_cv' | 'searching'
  -- | 'transferred_to_recruitment' | 'closed'
  auto_reply_paused BOOLEAN DEFAULT FALSE,  -- human takeover toggle
  -- What the candidate is looking for (kept light — Pandius is terse)
  candidate_context JSONB,               -- {desired_role, domain, location, notes}
  matched_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  -- Summary (LLM-generated, occasional)
  summary TEXT,
  -- Audit
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_activity_at TIMESTAMPTZ DEFAULT NOW(),
  closed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pandius_conv_client ON pandius_conversations(pandius_client_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pandius_conv_status ON pandius_conversations(status);

-- pandius_messages: complete audit trail of messages
CREATE TABLE IF NOT EXISTS pandius_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES pandius_conversations(id) ON DELETE CASCADE,
  pandius_client_id UUID NOT NULL REFERENCES pandius_clients(id) ON DELETE CASCADE,
  -- Message metadata
  direction TEXT NOT NULL,               -- 'inbound' | 'outbound'
  message_type TEXT DEFAULT 'text',      -- 'text' | 'document' | 'image' | 'system'
  green_api_message_id TEXT UNIQUE,      -- for deduplication
  -- Content
  text TEXT,
  document_url TEXT,                     -- CV download link from Green API
  document_filename TEXT,
  -- LLM context (for outbound messages)
  llm_invoked BOOLEAN DEFAULT FALSE,
  llm_model TEXT,
  llm_input_tokens INT,
  llm_output_tokens INT,
  -- Guard rails
  inappropriate_flag BOOLEAN DEFAULT FALSE,
  flag_reason TEXT,
  -- Audit
  sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pandius_messages_conv ON pandius_messages(conversation_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_pandius_messages_client ON pandius_messages(pandius_client_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_pandius_messages_green_api ON pandius_messages(green_api_message_id);
