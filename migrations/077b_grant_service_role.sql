-- Миграция 077b: Дать trudnik и trudnikapp наследование service_role
-- Необходимо для того, чтобы SET ROLE service_role работал через PostgREST
-- service_role нужен для обхода RLS в admin-запросах (postgrest_admin_request)

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnik') THEN
        GRANT anon, authenticated, service_role TO trudnik;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnikapp') THEN
        GRANT anon, authenticated, service_role TO trudnikapp;
    END IF;
END $$;