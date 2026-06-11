-- 017_recruiter_delivery_status.sql
-- Surface WhatsApp delivery outcome on a recruiter conversation so the operator
-- can SEE when an agent message (e.g. Elad's opening to a client) was stored but
-- NOT delivered — instead of the failure being buried in logs.

ALTER TABLE recruiter_conversations
    -- True/False = last outbound delivery succeeded/failed; NULL = none attempted.
    ADD COLUMN IF NOT EXISTS last_delivery_ok BOOLEAN,
    -- Machine reason when last_delivery_ok is false:
    -- 'no_phone' | 'invalid_phone' | 'not_configured' | 'green_api_error' | 'exception'
    ADD COLUMN IF NOT EXISTS last_delivery_reason TEXT,
    ADD COLUMN IF NOT EXISTS last_delivery_at TIMESTAMPTZ;

COMMENT ON COLUMN recruiter_conversations.last_delivery_reason IS 'Why the last agent message was not delivered (no_phone/invalid_phone/not_configured/green_api_error/exception); NULL when delivered';
