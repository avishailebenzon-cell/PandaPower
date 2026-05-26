-- Phase 10: Create Pandi bot tables
-- Clients, conversations, messages, referrals, quotas

-- pandi_clients: Client profiles for Pandi WhatsApp bot
CREATE TABLE pandi_clients (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Link to contacts (required — every Pandi client must have a contact)
  contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE RESTRICT,
  -- WhatsApp identification
  phone TEXT NOT NULL UNIQUE,           -- E.164 format (+972...)
  whatsapp_chat_id TEXT,                -- Green API chat_id (typically phone@c.us)
  -- Identification tracking
  identified_at TIMESTAMPTZ,            -- When first matched to contact
  identification_method TEXT,           -- 'auto_phone_match' | 'manual_intake_via_bot' | 'admin_assigned'
  initial_invite_sent_at TIMESTAMPTZ,   -- When SMS invite was sent
  initial_invite_sent_by_user_id UUID REFERENCES users(id),
  -- Interaction state
  is_active BOOLEAN DEFAULT TRUE,
  first_message_at TIMESTAMPTZ,
  last_message_at TIMESTAMPTZ,
  -- Intake flow (for unknown/new clients)
  intake_status TEXT DEFAULT 'not_started',
  -- 'not_started' | 'in_progress' | 'completed' | 'failed_no_response'
  intake_collected_data JSONB,          -- {name, company, role, referrer}
  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pandi_clients_phone ON pandi_clients(phone);
CREATE INDEX idx_pandi_clients_contact ON pandi_clients(contact_id);
CREATE INDEX idx_pandi_clients_active ON pandi_clients(is_active);

-- pandi_conversations: Chat sessions between client and Pandi
CREATE TABLE pandi_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pandi_client_id UUID NOT NULL REFERENCES pandi_clients(id) ON DELETE CASCADE,
  -- Conversation state
  status TEXT NOT NULL DEFAULT 'open',
  -- 'open' | 'awaiting_job_definition' | 'presenting_candidates'
  -- | 'awaiting_selection' | 'transferred_to_recruitment' | 'closed_idle'
  -- | 'closed_by_quota' | 'closed_by_admin'
  -- Job context
  job_context JSONB,                    -- {title, qualifications, location, security_clearance, must_have, nice_to_have, notes}
  matched_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  -- Summary (LLM-generated, updated ~every 10 messages)
  summary TEXT,
  -- Audit
  started_at TIMESTAMPTZ DEFAULT NOW(),
  last_activity_at TIMESTAMPTZ DEFAULT NOW(),
  closed_at TIMESTAMPTZ
);

CREATE INDEX idx_pandi_conv_client ON pandi_conversations(pandi_client_id, started_at DESC);
CREATE INDEX idx_pandi_conv_status ON pandi_conversations(status);

-- pandi_messages: Complete audit trail of messages
CREATE TABLE pandi_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES pandi_conversations(id) ON DELETE CASCADE,
  pandi_client_id UUID NOT NULL REFERENCES pandi_clients(id) ON DELETE CASCADE,
  -- Message metadata
  direction TEXT NOT NULL,              -- 'inbound' | 'outbound'
  message_type TEXT DEFAULT 'text',     -- 'text' | 'document' | 'image' | 'system'
  green_api_message_id TEXT UNIQUE,     -- For deduplication
  -- Content
  text TEXT,
  document_url TEXT,                    -- CV or document link
  document_filename TEXT,
  -- LLM context (for outbound messages)
  llm_invoked BOOLEAN DEFAULT FALSE,
  llm_model TEXT,
  llm_input_tokens INT,
  llm_output_tokens INT,
  llm_tools_called JSONB,
  -- Guard rails
  was_quota_blocked BOOLEAN DEFAULT FALSE,
  inappropriate_flag BOOLEAN DEFAULT FALSE,
  flag_reason TEXT,
  -- Audit
  sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pandi_messages_conv ON pandi_messages(conversation_id, sent_at);
CREATE INDEX idx_pandi_messages_client ON pandi_messages(pandi_client_id, sent_at DESC);
CREATE INDEX idx_pandi_messages_green_api ON pandi_messages(green_api_message_id);

-- candidate_referrals: Audit trail of candidates presented to clients
CREATE TABLE candidate_referrals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Who and to whom
  candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE RESTRICT,
  candidate_number TEXT NOT NULL,       -- Snapshot for external reference
  pandi_client_id UUID NOT NULL REFERENCES pandi_clients(id) ON DELETE RESTRICT,
  -- Context
  conversation_id UUID REFERENCES pandi_conversations(id) ON DELETE SET NULL,
  job_context JSONB,                    -- Snapshot of what client was looking for
  matched_job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  -- What was presented
  presented_at TIMESTAMPTZ DEFAULT NOW(),
  presented_payload JSONB NOT NULL,     -- Anonymized info sent to client
  llm_match_reasoning TEXT,             -- Why Pandi selected this candidate
  -- Status state machine (11 states)
  status TEXT NOT NULL DEFAULT 'presented',
  -- 'presented' | 'client_interested' | 'client_declined'
  -- | 'pending_full_cv_approval' | 'full_cv_approved' | 'full_cv_sent'
  -- | 'in_recruitment_process' | 'hired' | 'rejected_by_client'
  -- | 'rejected_by_us' | 'on_hold'
  status_updated_at TIMESTAMPTZ DEFAULT NOW(),
  status_updated_by_user_id UUID REFERENCES users(id),
  status_notes TEXT,
  -- Full CV approval workflow
  full_cv_approval_requested_at TIMESTAMPTZ,
  full_cv_approved_by_user_id UUID REFERENCES users(id),
  full_cv_approved_at TIMESTAMPTZ,
  full_cv_sent_at TIMESTAMPTZ,
  full_cv_pandi_message_id UUID REFERENCES pandi_messages(id) ON DELETE SET NULL,
  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  -- Constraint: same candidate can only be presented once per conversation
  UNIQUE(candidate_id, conversation_id)
);

CREATE INDEX idx_referrals_client ON candidate_referrals(pandi_client_id, presented_at DESC);
CREATE INDEX idx_referrals_candidate ON candidate_referrals(candidate_id);
CREATE INDEX idx_referrals_status ON candidate_referrals(status);

-- candidate_referral_history: Audit trail of status changes
CREATE TABLE candidate_referral_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  referral_id UUID NOT NULL REFERENCES candidate_referrals(id) ON DELETE CASCADE,
  -- State transition
  from_status TEXT,
  to_status TEXT NOT NULL,
  -- Who triggered it
  triggered_by_user_id UUID REFERENCES users(id),
  triggered_by_pandi_client_id UUID REFERENCES pandi_clients(id),
  -- Context
  reasoning TEXT,
  metadata JSONB,
  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_referral_history_referral ON candidate_referral_history(referral_id, created_at DESC);

-- pandi_message_quotas: Monthly message limits per client
CREATE TABLE pandi_message_quotas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pandi_client_id UUID NOT NULL REFERENCES pandi_clients(id) ON DELETE CASCADE,
  -- Calendar month
  month DATE NOT NULL,                  -- '2026-05-01' format
  -- Limits and usage
  monthly_limit INT NOT NULL DEFAULT 100,
  messages_used INT DEFAULT 0,
  -- Quota increase request workflow
  increase_requested_at TIMESTAMPTZ,
  increase_requested_amount INT,
  increase_approved_at TIMESTAMPTZ,
  increase_approved_by_user_id UUID REFERENCES users(id),
  increase_approved_amount INT,
  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  -- Constraint: one quota per client per month
  UNIQUE(pandi_client_id, month)
);

CREATE INDEX idx_quota_client_month ON pandi_message_quotas(pandi_client_id, month DESC);
CREATE INDEX idx_quota_increase_pending ON pandi_message_quotas(increase_requested_at)
  WHERE increase_requested_at IS NOT NULL AND increase_approved_at IS NULL;
