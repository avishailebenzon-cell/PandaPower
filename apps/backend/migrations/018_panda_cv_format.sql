-- 018_panda_cv_format.sql
-- "Panda-Tech format" CV generation for Elad's client delivery.
--
-- When a client approves receiving a candidate's CV, Elad must NOT forward the
-- raw uploaded file. Instead we render a clean, uniform branded CV (company
-- logo + iron number) from the structured data Claude already extracted, with
-- the candidate's personal contact channels replaced by PandaTech's own, so the
-- client always goes through us.
--
-- Because automatic extraction is never perfect, the rendered CV passes through
-- a human-in-the-loop review: it is generated, a person previews it and either
-- approves it (only then may it be sent to the client) or rejects it for
-- regeneration. These columns track that lifecycle per match.

ALTER TABLE matches
    -- Storage path (bucket "cvs") of the rendered Panda-Tech PDF. NULL until generated.
    ADD COLUMN IF NOT EXISTS formatted_cv_path TEXT,
    -- Review lifecycle of the rendered CV:
    --   'generated' | 'approved' | 'rejected' | NULL (not generated yet)
    ADD COLUMN IF NOT EXISTS formatted_cv_status TEXT,
    ADD COLUMN IF NOT EXISTS formatted_cv_generated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS formatted_cv_approved_at TIMESTAMPTZ,
    -- Who approved (free-text reviewer label; defaults to the admin email).
    ADD COLUMN IF NOT EXISTS formatted_cv_approved_by TEXT,
    -- Optional reviewer note when a generated CV is rejected for regeneration.
    ADD COLUMN IF NOT EXISTS formatted_cv_rejected_reason TEXT;

COMMENT ON COLUMN matches.formatted_cv_path IS 'Storage path (bucket cvs) of the rendered Panda-Tech branded CV PDF';
COMMENT ON COLUMN matches.formatted_cv_status IS 'Panda-Tech CV review lifecycle: generated | approved | rejected | NULL';
