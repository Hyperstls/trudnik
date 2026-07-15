-- Migration 124: PostgREST pre-request — materialize individual JWT claim GUCs
--
-- PROBLEM:
--   PostgREST v12/v14 exposes the full JWT only as `request.jwt.claims` (JSON).
--   The individual GUCs `request.jwt.claim.<name>` (user_id / role / app_role / ...)
--   are NOT set, so EVERY RLS policy written as
--       current_setting('request.jwt.claim.user_id', true)::uuid = id
--   evaluates to NULL → rows are filtered out. Symptoms: admin cannot open
--   /profile ("Не удалось загрузить профиль", status 200 but empty), and any
--   RLS-guarded user data is invisible.
--
-- FIX:
--   A PostgREST pre-request function copies the claims from the JSON blob into
--   the individual `request.jwt.claim.<name>` GUCs (transaction-local) before
--   the request query runs — so all existing RLS policies keep working unchanged.
--
--   This function MUST be combined with the PostgREST setting
--       PGRST_DB_PRE_REQUEST = pgrst_pre_request
--   (set on the trudnik-pr service). Apply THIS migration first, then set the env.
--
-- Idempotent (CREATE OR REPLACE + idempotent GRANT).

CREATE OR REPLACE FUNCTION public.pgrst_pre_request() RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    c json;
BEGIN
    c := nullif(current_setting('request.jwt.claims', true), '')::json;
    -- No JWT (anonymous request) — nothing to materialize.
    IF c IS NULL THEN
        RETURN;
    END IF;
    -- Only set GUCs for claims that are actually present, so that absent claims
    -- stay unset (current_setting(..., true) returns NULL, which RLS handles
    -- via OR-branches) instead of an empty string that would break ::uuid casts.
    IF c->>'role'     IS NOT NULL THEN PERFORM set_config('request.jwt.claim.role',     c->>'role',     true); END IF;
    IF c->>'app_role' IS NOT NULL THEN PERFORM set_config('request.jwt.claim.app_role', c->>'app_role', true); END IF;
    IF c->>'user_id'  IS NOT NULL THEN PERFORM set_config('request.jwt.claim.user_id',  c->>'user_id',  true); END IF;
    IF c->>'sub'      IS NOT NULL THEN PERFORM set_config('request.jwt.claim.sub',      c->>'sub',      true); END IF;
    IF c->>'email'    IS NOT NULL THEN PERFORM set_config('request.jwt.claim.email',    c->>'email',    true); END IF;
    IF c->>'jti'      IS NOT NULL THEN PERFORM set_config('request.jwt.claim.jti',      c->>'jti',      true); END IF;
END $$;

REVOKE EXECUTE ON FUNCTION public.pgrst_pre_request() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.pgrst_pre_request() TO anon, authenticated, service_role;
