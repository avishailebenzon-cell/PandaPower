-- Add job_opening_date to jobs.
-- The Pipedrive deals sync writes job_opening_date (derived from the deal's
-- add_time), but the column was never created, so every open deal failed to
-- sync with PGRST204 "Could not find the 'job_opening_date' column".
ALTER TABLE public.jobs
    ADD COLUMN IF NOT EXISTS job_opening_date timestamptz;
