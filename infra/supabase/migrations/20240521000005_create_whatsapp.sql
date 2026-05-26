-- Create whatsapp_conversations table
CREATE TABLE whatsapp_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_code TEXT NOT NULL,
  contact_phone TEXT NOT NULL,
  candidate_id UUID REFERENCES candidates(id),
  contact_id UUID REFERENCES contacts(id),
  related_match_id UUID REFERENCES matches(id),
  status TEXT,
  green_api_chat_id TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  summary TEXT,
  outcome TEXT,
  inappropriate_flag BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_whatsapp_phone ON whatsapp_conversations(contact_phone);
CREATE INDEX idx_whatsapp_status ON whatsapp_conversations(status);
CREATE INDEX idx_whatsapp_agent ON whatsapp_conversations(agent_code);
CREATE INDEX idx_whatsapp_candidate ON whatsapp_conversations(candidate_id);
CREATE INDEX idx_whatsapp_match ON whatsapp_conversations(related_match_id);
CREATE INDEX idx_whatsapp_created ON whatsapp_conversations(created_at DESC);

-- Create whatsapp_messages table
CREATE TABLE whatsapp_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES whatsapp_conversations(id) ON DELETE CASCADE,
  direction TEXT,
  message_text TEXT,
  message_type TEXT DEFAULT 'text',
  green_api_message_id TEXT,
  is_template BOOLEAN DEFAULT FALSE,
  template_name TEXT,
  flagged_inappropriate BOOLEAN DEFAULT FALSE,
  flag_reason TEXT,
  sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON whatsapp_messages(conversation_id, sent_at);
CREATE INDEX idx_messages_direction ON whatsapp_messages(direction);
