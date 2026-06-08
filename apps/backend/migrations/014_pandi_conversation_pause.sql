-- Migration: Pandi conversation pause (human takeover)
-- Date: 2026-06-08
-- Description: Adds auto_reply_paused to pandi_conversations so the operator can
-- temporarily disable Pandi's AI auto-reply for a conversation and answer the
-- client manually from the WhatsApp-style chat screen. The webhook worker
-- (workers/pandi/message_handler.py) checks this flag before letting Pandi
-- respond; inbound messages are still recorded while paused.

ALTER TABLE pandi_conversations
  ADD COLUMN IF NOT EXISTS auto_reply_paused BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN pandi_conversations.auto_reply_paused IS
  'When TRUE, Pandi''s AI auto-reply is paused — a human is writing as Pandi.';
