-- 051_fix_service_role_grants.sql
-- Исправляет права service_role на справочные таблицы (skills, religions, user_skills, job_skills).
-- Без этих прав supabase_admin_request (с apikey=service_role) не может выполнять
-- INSERT/UPDATE/DELETE на этих таблицах в локальном Supabase.
--
-- Проблема: в локальном Supabase заголовок apikey определяет роль, и Authorization
-- не всегда переопределяет её. При apikey=anon_key роль остаётся anon, у которой
-- нет прав на модификацию справочников. При apikey=service_role_key роль
-- становится service_role, но GRANT'ы на таблицы не были выданы.
--
-- Решение: выдать стандартные CRUD-права роли service_role на справочные таблицы.

GRANT SELECT, INSERT, UPDATE, DELETE ON public.skills TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.religions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_skills TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.job_skills TO service_role;
