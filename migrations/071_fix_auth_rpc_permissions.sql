-- 071: Fix auth RPC permissions for trudnikapp role
-- Проблема: RPC-функции login_user, register_user, change_password созданы
-- в миграции 067 без SET search_path = '' и могут быть недоступны для
-- trudnikapp из-за того, что GRANT anon/authenticated/service_role TO trudnikapp
-- был пропущен (exception handler в migration 067).

-- Также исправляем:
-- 1. SECURITY DEFINER функции теперь имеют SET search_path = ''
-- 2. Возвращаем service_role в GRANT для apply_job_atomic
-- 3. Принудительно даем trudnikapp права anon + authenticated + service_role

BEGIN;

-- ============================================================
-- ШАГ 1: Исправляем SECURITY DEFINER функции
-- ВАЖНО: CREATE OR REPLACE FUNCTION удалён, т.к. меняет return type
-- (RETURNS TABLE → RETURNS json), что запрещено в PostgreSQL.
-- Функции будут пересозданы через DROP + CREATE в migration 073.
-- GRANT-ы ниже работают независимо от return type.
-- ============================================================

-- Функции login_user, register_user, change_password
-- перенесены в migration 073 (DROP + CREATE).

-- ============================================================
-- ШАГ 2: GRANT EXECUTE на auth RPC-функции
-- ============================================================

GRANT EXECUTE ON FUNCTION public.login_user(text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.register_user(text, text, text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.change_password(uuid, text, text) TO anon, authenticated, service_role;

-- ============================================================
-- ШАГ 3: Принудительно даем trudnikapp права ролей
-- ============================================================

-- Если trudnikapp не существует — CREATE ROLE (необходимо для GRANT)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnikapp') THEN
        CREATE ROLE trudnikapp WITH LOGIN INHERIT;
    END IF;
END
$$;

-- Теперь безусловно даем inheritance от базовых ролей
GRANT anon TO trudnikapp;
GRANT authenticated TO trudnikapp;
GRANT service_role TO trudnikapp;

-- ============================================================
-- ШАГ 4: Исправляем apply_job_atomic (возвращаем service_role)
-- ============================================================

-- В migration 069 service_role был удален из GRANT-а
-- Возвращаем обратно
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO service_role;

-- ============================================================
-- ШАГ 5: Дополнительные GRANT-ы для всех RPC функций
-- (на случай, если предыдущие миграции их пропустили)
-- ============================================================

-- RPC функции из migration 069
GRANT EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.complete_job(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.cancel_job(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rate_worker(uuid, uuid, integer, text) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;

COMMIT;
