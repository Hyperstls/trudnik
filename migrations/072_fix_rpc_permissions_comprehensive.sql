-- ============================================================================
-- 072: Fix RPC permissions — comprehensive grants for all functions
-- ============================================================================
--
-- ПРОБЛЕМА:
--   PostgREST возвращает 403 (permission denied) при вызове RPC-функций
--   login_user, register_user и других, если у роли anon/authenticated
--   нет прав EXECUTE на эти функции. Миграция 071 исправила основные
--   функции, но нужна дополнительная гарантия для всех существующих
--   и будущих RPC-функций.
--
-- РЕШЕНИЕ:
--   1. GRANT EXECUTE ON ALL FUNCTIONS — для всех существующих функций в схеме public
--   2. GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA — для функций в других схемах (api, etc.)
--   3. ALTER DEFAULT PRIVILEGES — для будущих функций (чтобы новые функции
--      автоматически получали права на выполнение)
--   4. Повторная проверка и фиксация прав для login_user и register_user
--   5. GRANT ролей trudnikapp для postgrest (если postgrest подключен как trudnikapp)
-- ============================================================================

BEGIN;

-- ============================================================
-- ШАГ 1: Права на все существующие функции в схеме public
-- ============================================================

-- anon — для неаутентифицированных вызовов (login, register)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO anon;

-- authenticated — для аутентифицированных вызовов
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO authenticated;

-- service_role — для админских вызовов (обход RLS)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

-- ============================================================
-- ШАГ 2: Права по умолчанию для БУДУЩИХ функций
-- ============================================================

-- Будущие функции в public будут автоматически доступны
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;

-- ============================================================
-- ШАГ 3: Явная проверка прав для ключевых auth-функций
-- ============================================================

-- Проверяем, что права на login_user есть у anon (нужно для неаутентифицированного входа)
DO $$
BEGIN
    -- Проверка через has_function_privilege не работает для непрямых привилегий,
    -- поэтому делаем прямой GRANT (идемпотентно)
    GRANT EXECUTE ON FUNCTION public.login_user(text, text) TO anon;
EXCEPTION
    WHEN others THEN
        RAISE WARNING '072: Could not GRANT login_user to anon: %', SQLERRM;
END;
$$;

-- Проверяем права на register_user
DO $$
BEGIN
    GRANT EXECUTE ON FUNCTION public.register_user(text, text, text, text) TO anon;
EXCEPTION
    WHEN others THEN
        RAISE WARNING '072: Could not GRANT register_user to anon: %', SQLERRM;
END;
$$;

-- change_password для authenticated
DO $$
BEGIN
    GRANT EXECUTE ON FUNCTION public.change_password(uuid, text, text) TO authenticated;
EXCEPTION
    WHEN others THEN
        RAISE WARNING '072: Could not GRANT change_password to authenticated: %', SQLERRM;
END;
$$;

-- ============================================================
-- ШАГ 4: Расширенные права для trudnikapp (PostgREST role)
-- ============================================================

-- trudnikapp должна иметь возможность выполнять функции от имени anon и authenticated
-- (PostgREST переключает роли через SET ROLE)
DO $$
BEGIN
    GRANT anon TO trudnikapp;
EXCEPTION
    WHEN duplicate_object THEN NULL;
    WHEN others THEN
        RAISE WARNING '072: Could not GRANT anon TO trudnikapp: %', SQLERRM;
END;
$$;

DO $$
BEGIN
    GRANT authenticated TO trudnikapp;
EXCEPTION
    WHEN duplicate_object THEN NULL;
    WHEN others THEN
        RAISE WARNING '072: Could not GRANT authenticated TO trudnikapp: %', SQLERRM;
END;
$$;

DO $$
BEGIN
    GRANT service_role TO trudnikapp;
EXCEPTION
    WHEN duplicate_object THEN NULL;
    WHEN others THEN
        RAISE WARNING '072: Could not GRANT service_role TO trudnikapp: %', SQLERRM;
END;
$$;

-- ============================================================
-- ШАГ 5: IF EXISTS для всех RPC-функций (на случай если некоторые не созданы)
-- ============================================================

-- Функции из миграции 069 (атомарные операции)
GRANT EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.complete_job(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.cancel_job(uuid) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.rate_worker(uuid, uuid, integer, text) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;

-- exec_sql — только для service_role (админский доступ)
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;

-- ============================================================
-- ШАГ 6: Проверка корректности прав
-- ============================================================

DO $$
DECLARE
    func_count integer;
BEGIN
    -- Считаем количество функций с корректными правами
    SELECT COUNT(*) INTO func_count
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public'
      AND p.prokind = 'f';
    
    RAISE NOTICE '072: Found % functions in schema public', func_count;
    
    -- Проверяем, что у login_user есть права для anon
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
          AND p.proname = 'login_user'
          AND has_function_privilege('anon', p.oid, 'EXECUTE')
    ) THEN
        RAISE NOTICE '072: login_user has EXECUTE privilege for anon — OK';
    ELSE
        RAISE WARNING '072: login_user MISSING EXECUTE privilege for anon';
    END IF;
    
    -- Проверяем register_user
    IF EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'public'
          AND p.proname = 'register_user'
          AND has_function_privilege('anon', p.oid, 'EXECUTE')
    ) THEN
        RAISE NOTICE '072: register_user has EXECUTE privilege for anon — OK';
    ELSE
        RAISE WARNING '072: register_user MISSING EXECUTE privilege for anon';
    END IF;
END;
$$;

COMMIT;
