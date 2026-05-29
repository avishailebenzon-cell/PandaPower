-- Migration: Recruiter Conversations System
-- Date: 2026-05-29
-- Description: Add tables for Tal and Elad recruiter conversations

-- Create recruiter_conversations table for Tal/Elad conversations
CREATE TABLE IF NOT EXISTS recruiter_conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  match_id UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  recruiter TEXT NOT NULL CHECK (recruiter IN ('tal', 'elad')),
  started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  ended_at TIMESTAMP WITH TIME ZONE,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'closed', 'pending')),
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create recruiter_messages table for conversation messages
CREATE TABLE IF NOT EXISTS recruiter_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES recruiter_conversations(id) ON DELETE CASCADE,
  recruiter TEXT NOT NULL CHECK (recruiter IN ('tal', 'elad')),
  direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  message_type TEXT DEFAULT 'text' CHECK (message_type IN ('text', 'file', 'image', 'audio')),
  text TEXT,
  file_url TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_recruiter_conversations_match_id ON recruiter_conversations(match_id);
CREATE INDEX IF NOT EXISTS idx_recruiter_conversations_recruiter ON recruiter_conversations(recruiter);
CREATE INDEX IF NOT EXISTS idx_recruiter_conversations_status ON recruiter_conversations(status);
CREATE INDEX IF NOT EXISTS idx_recruiter_conversations_started_at ON recruiter_conversations(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_recruiter_messages_conversation_id ON recruiter_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_recruiter_messages_recruiter ON recruiter_messages(recruiter);
CREATE INDEX IF NOT EXISTS idx_recruiter_messages_created_at ON recruiter_messages(created_at DESC);

-- Add comments for documentation
COMMENT ON TABLE recruiter_conversations IS 'Conversations between Tal/Elad recruiters and candidates/clients';
COMMENT ON COLUMN recruiter_conversations.recruiter IS 'Which recruiter: tal (initial screening) or elad (client offers)';
COMMENT ON COLUMN recruiter_conversations.status IS 'Conversation status: active (ongoing), closed (ended), pending (scheduled)';
COMMENT ON TABLE recruiter_messages IS 'Individual messages within recruiter conversations';
COMMENT ON COLUMN recruiter_messages.direction IS 'inbound (from candidate/client) or outbound (from recruiter)';
