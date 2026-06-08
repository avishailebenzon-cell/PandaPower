-- 016_elad_placement_flow.sql
-- Elad's client-facing placement flow.
--
-- Elad is a SALES agent who presents a *vetted* candidate to the CLIENT (the
-- company that opened the job), in sales language, WITHOUT the candidate's
-- personal contact details (no phone/email). The candidate is tracked by an
-- "iron number" (REF-2026-XXXX) for the whole client conversation, until the
-- full CV (with personal details) is sent — and only after the client's
-- explicit approval.
--
-- Three visible statuses progress automatically from the conversation:
--   1. client_contacted  — Elad reached out to the client
--   2. details_sent      — Elad presented the candidate's full (anonymised) profile
--   3. cv_sent           — the original CV file was sent to the client (after approval)

ALTER TABLE matches
    -- The candidate's "iron number" for this placement (REF-2026-XXXX). Stable
    -- for the life of the match; shown to the client instead of the name only
    -- when we want an anonymous handle, but mainly an internal/forward ref.
    ADD COLUMN IF NOT EXISTS iron_number TEXT,
    -- Elad's sub-stage within the client conversation. NULL until Elad starts.
    -- Values: 'client_contacted' | 'details_sent' | 'awaiting_cv_decision'
    --         | 'cv_sent' | 'cv_declined'
    ADD COLUMN IF NOT EXISTS elad_stage TEXT,
    ADD COLUMN IF NOT EXISTS elad_details_sent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS elad_cv_offered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS elad_cv_sent_at TIMESTAMPTZ,
    -- 'approved' | 'declined' | NULL (the client's explicit choice on the CV)
    ADD COLUMN IF NOT EXISTS elad_cv_decision TEXT;

-- Fast lookup of the next sequential iron number.
CREATE INDEX IF NOT EXISTS idx_matches_iron_number ON matches (iron_number);

COMMENT ON COLUMN matches.iron_number IS 'Candidate "iron number" REF-2026-XXXX used in the client conversation until the full CV is shared';
COMMENT ON COLUMN matches.elad_stage IS 'Elad client-flow stage: client_contacted | details_sent | awaiting_cv_decision | cv_sent | cv_declined';
