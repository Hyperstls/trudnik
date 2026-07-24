-- ============================================================================
-- Migration 132: Restrict sensitive profile columns from anon/authenticated
-- ============================================================================
-- PROBLEM (P0): migration 123 grants TABLE-LEVEL SELECT on all tables to
--   anon/authenticated. Combined with the permissive profiles read-policy,
--   anon could read password_hash + email of every profile.
--
-- FIX: narrow profiles to COLUMN-LEVEL grants. Done DYNAMICALLY (reads actual
--   columns from information_schema) so it never fails on dev/prod schema
--   divergence (e.g. local has avatar_url, prod does not). All CURRENT columns
--   are granted EXCEPT the sensitive set, to BOTH anon and authenticated.
--   service_role (BYPASSRLS) is unaffected; login RPC is SECURITY DEFINER.
--
-- Sensitive (never client-readable): password_hash, email, inn, phone,
--   verification_doc_url, notification_prefs, search_vector.
--
-- DURABILITY: ensure_postgrest_role_grants re-applies this every cycle so the
--   restriction survives 123's table-level re-GRANT on role-membership resets.
-- Idempotent.
-- ============================================================================

BEGIN;

REVOKE SELECT ON public.profiles FROM anon;
REVOKE SELECT ON public.profiles FROM authenticated;

DO $$
DECLARE
    c text;
    v_sensitive text[] := ARRAY[
        'password_hash', 'email', 'inn', 'phone',
        'verification_doc_url', 'notification_prefs', 'search_vector'
    ];
BEGIN
    FOR c IN
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'profiles'
          AND NOT (column_name = ANY(v_sensitive))
    LOOP
        EXECUTE format('GRANT SELECT (%I) ON public.profiles TO anon', c);
        EXECUTE format('GRANT SELECT (%I) ON public.profiles TO authenticated', c);
    END LOOP;
END $$;

COMMIT;
