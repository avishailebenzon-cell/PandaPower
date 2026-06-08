-- Migration: Tal Conversation Screen (WhatsApp-style)
-- Date: 2026-06-08
-- Description: Adds the columns the Tal conversations screen needs:
--   • recruiter_conversations.auto_reply_paused — when TRUE, Tal's AI auto-reply
--     is temporarily disabled for this conversation. A human is "taking over"
--     and writing as Tal; the agent stays quiet until the toggle is flipped back.
--   • recruiter_messages.author — distinguishes who actually produced an
--     outbound message: 'agent' (Tal's AI), 'human' (the operator writing as
--     Tal), or 'candidate' (inbound). Lets the UI subtly mark human takeovers.
--   • recruiter_conversations.candidate_phone — cached WhatsApp number so inbound
--     Green-API webhooks can route a message straight to the right conversation
--     without re-joining through matches→candidates every time.

ALTER TABLE recruiter_conversations
  ADD COLUMN IF NOT EXISTS auto_reply_paused BOOLEAN DEFAULT FALSE;

ALTER TABLE recruiter_conversations
  ADD COLUMN IF NOT EXISTS candidate_phone TEXT;

ALTER TABLE recruiter_messages
  ADD COLUMN IF NOT EXISTS author TEXT DEFAULT 'agent'
  CHECK (author IN ('agent', 'human', 'candidate'));

CREATE INDEX IF NOT EXISTS idx_recruiter_conversations_candidate_phone
  ON recruiter_conversations(candidate_phone);

COMMENT ON COLUMN recruiter_conversations.auto_reply_paused IS
  'When TRUE, Tal''s AI auto-reply is paused — a human is writing as Tal.';
COMMENT ON COLUMN recruiter_conversations.candidate_phone IS
  'Cached candidate WhatsApp number (digits only) for inbound webhook routing.';
COMMENT ON COLUMN recruiter_messages.author IS
  'Who produced the message: agent (Tal AI), human (operator as Tal), candidate.';
