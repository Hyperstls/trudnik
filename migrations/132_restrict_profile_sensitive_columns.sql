-- ============================================================================
-- Migration 132: Restrict sensitive profile columns from anon/authenticated
-- ============================================================================
-- PROBLEM (P0 security, found in audit):
--   Migration 123 grants TABLE-LEVEL SELECT on ALL tables to anon & authenticated
--   (lines 87-88). Combined with the permissive profiles read-policy
--   (`jwt.user_id = id OR role IN ('worker','employer')`), ANY anonymous user can
--   read password_hash + email of EVERY profile:
--     GET /profiles?select=password_hash,email   (no Authorization)  -> leaks hashes
--   Root cause: table-level GRANT exposes all columns; RLS is row-level and can't
--   hide individual columns.
--
-- FIX:
--   Narrow profiles to COLUMN-LEVEL grants. anon sees only public (non-PII)
--   columns; authenticated sees all except password_hash (login RPC is SECURITY
--   DEFINER and reads the hash server-side, so no client role needs it).
--   service_role (BYPASSRLS) is unaffected.
--
-- DURABILITY: ensure_postgrest_role_grants (Celery beat) re-applies migration 123
--   (table-level GRANT) on role-membership loss. The self-heal task was updated to
--   re-apply THIS migration (132) every cycle, so the column restriction survives.
--
-- Idempotent: REVOKE/GRANT are safe to re-run.
-- ============================================================================

BEGIN;

-- 1) Remove table-level SELECT on profiles (re-granted per-column below)
REVOKE SELECT ON public.profiles FROM anon;
REVOKE SELECT ON public.profiles FROM authenticated;

-- 2) anon: only PUBLIC columns (no email / phone / inn / password_hash / docs / prefs)
GRANT SELECT (
    id, role, full_name, photo_url, avatar_url, age, bio, city, experience,
    desired_payment, verification_status, rating, total_reviews, ratings_count,
    religion_id, portfolio_link, is_self_employed, email_public, contact,
    created_at, updated_at, email_verified, consented_at, password_changed_at
) ON public.profiles TO anon;

-- 3) authenticated: all columns EXCEPT password_hash (own email/phone/inn/docs
--    are readable via the self-row RLS policy; password_hash never client-side)
GRANT SELECT (
    id, role, full_name, phone, photo_url, avatar_url, age, bio, city, experience,
    desired_payment, verification_status, verification_doc_url, rating, total_reviews,
    ratings_count, religion_id, portfolio_link, inn, is_self_employed, email_public,
    contact, notification_prefs, email, created_at, updated_at, email_verified,
    consented_at, password_changed_at
) ON public.profiles TO authenticated;

-- search_vector: granted to NEITHER role (internal FTS column, service_role only).

COMMIT;
