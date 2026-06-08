-- Migration 012: Dana (AI sales agent) conversation storage.
-- Dana intakes new job deals via free-form web chat (+ file uploads),
-- collects all role details into job_context, then opens a Pipedrive deal.

CREATE TABLE IF NOT EXISTS public.dana_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT,
    status TEXT DEFAULT 'open',          -- open | deal_created
    job_context JSONB DEFAULT '{}'::jsonb,
    pipedrive_deal_id INT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dana_conversations_status
    ON public.dana_conversations (status);
CREATE INDEX IF NOT EXISTS idx_dana_conversations_updated
    ON public.dana_conversations (updated_at DESC);

CREATE TABLE IF NOT EXISTS public.dana_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES public.dana_conversations(id) ON DELETE CASCADE,
    direction TEXT NOT NULL,             -- inbound | outbound
    text TEXT,
    llm_model TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dana_messages_conversation
    ON public.dana_messages (conversation_id, sent_at);
