-- Add a geographic-mismatch flag to matches.
--
-- A candidate can be an excellent fit for a job on skills/experience/clearance
-- yet live too far from the job's location to commute. We do NOT drop such a
-- match (some candidates will relocate for the right role) — instead the
-- matching agent (Claude) flags it, and every table that shows the match
-- renders a bold red "אין התאמה גיאוגרפית" badge so Carmit/Tal can make an
-- informed decision about whether to promote it to a Tal conversation.
--
-- geographic_mismatch:        TRUE when the agent judged the candidate's
--                             location incompatible with the job's location.
-- geographic_mismatch_reason: short Hebrew explanation (e.g. which cities and
--                             the rough distance) shown on hover / in the modal.

ALTER TABLE matches
    ADD COLUMN IF NOT EXISTS geographic_mismatch BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS geographic_mismatch_reason TEXT;
