-- Migration 130: Fix auth RPC search_path for pgcrypto (gen_salt/crypt)
--
-- PROBLEM: register_user / login_user / change_password use pgcrypto
-- functions crypt() and gen_salt('bf', 12) (installed in schema `public`),
-- but were created with `SET search_path = ''` (empty). With an empty
-- search_path PostgreSQL cannot resolve gen_salt, so registration fails:
--   "function gen_salt(unknown, integer) does not exist"
-- (Same class of bug as the PostGIS functions fixed in migration 127 —
--  rule 04 exception: extension-dependent functions need search_path.)
--
-- FIX: set the functions' search_path to pg_catalog, public so the pgcrypto
-- helpers resolve. ALTER FUNCTION ... SET search_path only changes the
-- setting — the body is untouched. Idempotent.
--
-- Note: login_user is also called by the direct-SQL fallback (psycopg2),
-- which has a normal search_path and works; this fixes the RPC path used by
-- PostgREST and password change.

ALTER FUNCTION public.register_user(text, text, text, text) SET search_path = pg_catalog, public;
ALTER FUNCTION public.login_user(text, text) SET search_path = pg_catalog, public;
ALTER FUNCTION public.change_password(uuid, text, text) SET search_path = pg_catalog, public;

-- Same class of bug: delete_user_cascade / delete_job_cascade were created with
-- SET search_path = '' but reference tables UNQUALIFIED (applications, notifications,
-- favorites, ...). With an empty search_path PostgreSQL can't resolve them, so admin
-- user/job deletion fails ("relation does not exist"). delete_user_cascade also calls
-- delete_job_cascade() unqualified (employer branch).
ALTER FUNCTION public.delete_user_cascade(uuid) SET search_path = pg_catalog, public;
ALTER FUNCTION public.delete_job_cascade(uuid) SET search_path = pg_catalog, public;
