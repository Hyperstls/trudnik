-- Migration 123: Fix PostgREST "permission denied to set role" (CRITICAL)
--
-- PROBLEM (production):
--   /health/postgrest returns 401: {"code":"42501","message":"permission denied to set role \"anon\""}
--   PostgREST connects to PostgreSQL as role `trudnikapp` (PGRST_DB_URI).
--   Migration 067 tried `GRANT anon,authenticated,service_role TO trudnikapp` inside a
--   DO-block that silently skipped (RAISE NOTICE) when trudnikapp did not yet exist
--   (CloudNativePG creates trudnikapp AFTER migrations run). The grant was never re-applied.
--
--   Consequence: SET ROLE anon/authenticated fails for EVERY user-JWT and anonymous
--   request → all `postgrest_request` (authenticated) calls return 401 → Circuit Breaker
--   OPEN → empty dictionaries, empty jobs list, registration fails, login_required
--   degrades. Only service_role (postgrest_admin_request) keeps working.
--
-- FIX:
--   1. Re-grant anon/authenticated/service_role TO trudnikapp (and CURRENT_USER) so
--      PostgREST can SET ROLE for anonymous, authenticated and service requests.
--   2. GRANT SELECT on public dictionaries (skills, religions) TO anon, authenticated
--      so registration/profile dropdowns load via user-JWT (currently only service_role
--      has SELECT — see 067 lines 2269-2270).
--
-- Idempotent: GRANT is safe to re-run; DO-blocks guard optional roles.

-- ────────────────────────────────────────────────────────────
-- 1. Ensure the three PostgREST roles exist (NOLOGIN)
-- ────────────────────────────────────────────────────────────
DO $$ BEGIN
    CREATE ROLE anon WITH NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE ROLE authenticated WITH NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE ROLE service_role WITH NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- service_role bypasses RLS for admin/server-side operations
ALTER ROLE service_role WITH BYPASSRLS;

-- ────────────────────────────────────────────────────────────
-- 2. THE KEY FIX: let the PostgREST connection role switch into
--    anon/authenticated/service_role. Without this, every
--    `SET LOCAL ROLE <jwt-role>` fails with 42501.
-- ────────────────────────────────────────────────────────────
-- trudnikapp = the role PostgREST connects as in production (Amvera/CloudNativePG).
GRANT anon, authenticated, service_role TO trudnikapp;

-- CURRENT_USER = whoever applies this migration (local dev superuser, etc.)
GRANT anon, authenticated, service_role TO CURRENT_USER;

-- Belt-and-suspenders: also grant to the legacy local Docker role if it exists.
DO $$ BEGIN
    GRANT anon, authenticated, service_role TO trudnik;
EXCEPTION WHEN undefined_object THEN NULL;
END $$;

-- ────────────────────────────────────────────────────────────
-- 3. Public-read SELECT on dictionaries (needed before login,
--    during registration and on the worker profile editor).
--    Previously only service_role had SELECT (067 L2269-2270).
-- ────────────────────────────────────────────────────────────
GRANT SELECT ON public.skills     TO anon, authenticated;
GRANT SELECT ON public.religions  TO anon, authenticated;

-- Ensure public read RLS policies are in place
DROP POLICY IF EXISTS "read_skills"    ON skills;
CREATE POLICY "read_skills"    ON skills    FOR SELECT USING (true);

DROP POLICY IF EXISTS "read_religions" ON religions;
CREATE POLICY "read_religions" ON religions FOR SELECT USING (true);

-- ────────────────────────────────────────────────────────────
-- 4. Table-level DML for the PostgREST JWT roles.
--    The standard PostgREST model: grant SELECT/INSERT/UPDATE/DELETE to the
--    anon/authenticated roles and enforce row isolation via RLS. The local
--    Docker DB has exactly these grants, but they were never captured in a
--    tracked migration — so production (Amvera/CloudNativePG) is missing them,
--    and every user-JWT query fails (403 "permission denied for table …") even
--    after the SET ROLE fix above. RLS is enabled on all business tables, so
--    these grants are safe (rows are still filtered per-user).
-- ────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon;

-- Sequences (needed for INSERT into tables with SERIAL/identity columns)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon;

-- Default privileges: future tables created by the app role inherit the grants
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO anon;
