-- Migration 078: Drop exec_sql RPC
-- Security: exec_sql(text) allowed arbitrary SQL execution.
-- Anyone with PGRST_JWT_SECRET had root access to the database.
-- Replaced by CLI-only psycopg2 connections in scripts.

-- DROP IF EXISTS + REVOKE обёрнуты в DO-блок для безопасности
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'exec_sql' AND pronamespace = 'public'::regnamespace) THEN
        REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM service_role;
        DROP FUNCTION public.exec_sql(text) CASCADE;
    END IF;
END $$;
