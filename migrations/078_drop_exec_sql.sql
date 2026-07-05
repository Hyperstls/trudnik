-- Migration 078: Drop exec_sql RPC
-- Security: exec_sql(text) allowed arbitrary SQL execution.
-- Anyone with PGRST_JWT_SECRET had root access to the database.
-- Replaced by CLI-only psycopg2 connections in scripts.

DROP FUNCTION IF EXISTS public.exec_sql(text) CASCADE;
REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM service_role;
