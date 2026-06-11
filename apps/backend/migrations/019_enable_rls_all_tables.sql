-- Migration 019: Enable Row Level Security on all public tables
--
-- WHY: Every table in the `public` schema without RLS is reachable via the
-- Supabase anon key (the public key shipped to browsers). Anyone with that key
-- could read/write/delete data directly through Supabase's REST API.
--
-- SAFE FOR THIS APP: The frontend never talks to Supabase directly — all DB
-- access goes through the FastAPI backend using the SERVICE ROLE key, which
-- BYPASSES RLS. So enabling RLS with NO policies locks out anon/public access
-- while leaving the backend fully functional.
--
-- Idempotent: re-running is safe. ENABLE/FORCE on an already-secured table is a no-op.

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', r.tablename);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY;', r.tablename);
  END LOOP;
END $$;

-- Verification (should return 0 rows):
--   SELECT tablename FROM pg_tables
--   WHERE schemaname = 'public' AND rowsecurity = false;
