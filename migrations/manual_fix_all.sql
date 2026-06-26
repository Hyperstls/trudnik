-- ============================================================
-- manual_fix_all.sql
-- Полный скрипт для ручного применения через pgAdmin.
-- Объединяет миграции 071, 072 и 073.
--
-- ВНИМАНИЕ: GRANT EXECUTE выдаётся ТОЛЬКО на реально существующие
-- SQL-функции: login_user, register_user, change_password.
-- Остальные "rpc" (complete_job, cancel_job, apply_to_job и т.д.)
-- являются HTTP-эндпоинтами PostgREST, а не SQL-функциями.
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public удалён как опасный.
-- ============================================================

-- ============================================================
-- 071: Права на auth-функции
-- ============================================================

-- Создаём роль trudnikapp, если её нет
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnikapp') THEN
        CREATE ROLE trudnikapp WITH LOGIN PASSWORD NULL;
    END IF;
END
$$;

-- Даём права на логин
GRANT EXECUTE ON FUNCTION login_user(TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION register_user(TEXT, TEXT, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION change_password(UUID, TEXT, TEXT) TO authenticated, service_role;

-- trudnikapp должен наследовать права от базовых ролей, а не наоборот
GRANT anon TO trudnikapp;
GRANT authenticated TO trudnikapp;
GRANT service_role TO trudnikapp;

-- ============================================================
-- 072: ALTER DEFAULT PRIVILEGES (безопасно — только на будущие функции)
-- ============================================================

ALTER DEFAULT PRIVILEGES FOR ROLE trudnikapp IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO anon, authenticated, service_role;

-- ============================================================
-- 073: Пересоздание auth-функций (SECURITY DEFINER + search_path)
-- ============================================================

-- Сначала удаляем старые функции
DROP FUNCTION IF EXISTS login_user(TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS register_user(TEXT, TEXT, TEXT, TEXT) CASCADE;
DROP FUNCTION IF EXISTS change_password(UUID, TEXT, TEXT) CASCADE;

-- Создаём заново с SECURITY DEFINER и SET search_path = ''
CREATE OR REPLACE FUNCTION login_user(p_email TEXT, p_password TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_user RECORD;
BEGIN
    SELECT id, email, role, full_name, password_hash
    INTO v_user
    FROM public.users
    WHERE email = p_email AND is_active = true;

    IF v_user.id IS NULL THEN
        RETURN json_build_object('error', 'User not found');
    END IF;

    IF NOT(v_user.password_hash = crypt(p_password, v_user.password_hash)) THEN
        RETURN json_build_object('error', 'Invalid password');
    END IF;

    RETURN row_to_json(v_user);
END;
$$;

-- Регистрация
CREATE OR REPLACE FUNCTION register_user(p_email TEXT, p_password TEXT, p_role TEXT, p_full_name TEXT)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    INSERT INTO public.users (email, password_hash, role, full_name)
    VALUES (p_email, crypt(p_password, gen_salt('bf')), p_role, p_full_name)
    RETURNING id INTO v_user_id;

    RETURN v_user_id;
END;
$$;

-- Смена пароля
CREATE OR REPLACE FUNCTION change_password(p_user_id UUID, p_old_password TEXT, p_new_password TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_stored_hash TEXT;
BEGIN
    SELECT password_hash INTO v_stored_hash
    FROM public.users
    WHERE id = p_user_id;

    IF v_stored_hash = crypt(p_old_password, v_stored_hash) THEN
        UPDATE public.users
        SET password_hash = crypt(p_new_password, gen_salt('bf'))
        WHERE id = p_user_id;
        RETURN TRUE;
    END IF;

    RETURN FALSE;
END;
$$;

-- Повторно выдаём права (после DROP/CREATE права сбрасываются)
GRANT EXECUTE ON FUNCTION login_user(TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION register_user(TEXT, TEXT, TEXT, TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION change_password(UUID, TEXT, TEXT) TO authenticated, service_role;

-- ============================================================
-- Верификация: проверяем только реально существующие функции
-- ============================================================
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM information_schema.routine_privileges
    WHERE grantee IN ('anon', 'authenticated', 'service_role')
      AND privilege_type = 'EXECUTE'
      AND routine_name IN ('login_user', 'register_user', 'change_password');
    RAISE INFO 'Проверка: найдено % привилегий EXECUTE для auth-функций', v_count;
END;
$$;

-- ============================================================
-- 074: Исправление RLS-политик для admin_skills и admin_religions
-- Проблема: postgrest_admin_request() использует JWT с role='trudnikapp',
-- но RLS-политики ожидают role='admin'. Из-за этого INSERT отклоняется (403).
--
-- Решение: добавить 'trudnikapp' как разрешённую роль в политики.
-- ============================================================

DROP POLICY IF EXISTS "admin_skills" ON skills;
CREATE POLICY "admin_skills" ON skills FOR ALL
    USING (current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp'));

DROP POLICY IF EXISTS "admin_religions" ON religions;
CREATE POLICY "admin_religions" ON religions FOR ALL
    USING (current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp'));

DROP POLICY IF EXISTS "receipts_insert" ON receipts;
CREATE POLICY "receipts_insert" ON receipts
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp')
    );

DROP POLICY IF EXISTS "receipts_update" ON receipts;
CREATE POLICY "receipts_update" ON receipts
    FOR UPDATE USING (
        current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp')
    );
