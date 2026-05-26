-- Create telegram_users table
CREATE TABLE telegram_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_chat_id BIGINT UNIQUE NOT NULL,
  telegram_username TEXT,
  telegram_first_name TEXT,
  linked_user_id UUID,
  is_authorized BOOLEAN DEFAULT FALSE,
  is_admin BOOLEAN DEFAULT FALSE,
  notification_preferences JSONB DEFAULT '{
    "high_priority_match": true,
    "ingestion_errors": true,
    "tal_positive_response": true,
    "daily_summary": true,
    "daily_summary_time": "08:30"
  }'::jsonb,
  authorized_at TIMESTAMPTZ,
  authorized_by_user_id UUID,
  last_message_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_telegram_users_chat_id ON telegram_users(telegram_chat_id);
CREATE INDEX idx_telegram_users_authorized ON telegram_users(is_authorized);
CREATE INDEX idx_telegram_users_admin ON telegram_users(is_admin);

-- Create telegram_messages table
CREATE TABLE telegram_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_user_id UUID REFERENCES telegram_users(id) ON DELETE CASCADE,
  direction TEXT NOT NULL,
  message_type TEXT DEFAULT 'text',
  telegram_message_id BIGINT,
  command TEXT,
  command_args TEXT,
  text TEXT,

  -- LLM context
  llm_invoked BOOLEAN DEFAULT FALSE,
  llm_tools_called JSONB,
  llm_tokens_used INT,

  -- Callback queries
  callback_action TEXT,
  callback_data JSONB,
  related_match_id UUID REFERENCES matches(id),
  related_job_id UUID REFERENCES jobs(id),

  -- Notification trigger
  notification_event TEXT,

  -- Meta
  sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_telegram_messages_user ON telegram_messages(telegram_user_id, sent_at DESC);
CREATE INDEX idx_telegram_messages_match ON telegram_messages(related_match_id);
CREATE INDEX idx_telegram_messages_command ON telegram_messages(command);
