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
-- ============================================================

-- 1.1 login_user
CREATE OR REPLACE FUNCTION public.login_user(
    email text,
    password text
) RETURNS json
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = ''
AS $$
DECLARE
    user_record record;
BEGIN
    SELECT id, email, role, full_name
    INTO user_record
    FROM public.profiles
    WHERE email = login_user.email
      AND password_hash = public.crypt(login_user.password, password_hash);

    IF NOT FOUND THEN
        RETURN json_build_object('error', 'invalid_credentials');
    END IF;

    RETURN json_build_object(
        'user_id', user_record.id,
        'email', user_record.email,
        'role', user_record.role,
        'full_name', user_record.full_name
    );
END;
$$;

-- 1.2 register_user
CREATE OR REPLACE FUNCTION public.register_user(
    email text,
    password text,
    role text DEFAULT 'worker',
    full_name text DEFAULT NULL
) RETURNS json
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = ''
AS $$
DECLARE
    new_user_id uuid;
BEGIN
    -- Проверяем, что email не занят
    IF EXISTS (SELECT 1 FROM public.profiles WHERE email = register_user.email) THEN
        RETURN json_build_object('error', 'email_exists');
    END IF;

    new_user_id := public.gen_random_uuid();

    INSERT INTO public.profiles (id, email, password_hash, role, full_name)
    VALUES (
        new_user_id,
        register_user.email,
        public.crypt(register_user.password, public.gen_salt('bf')),
        register_user.role,
        COALESCE(register_user.full_name, '')
    );

    RETURN json_build_object(
        'user_id', new_user_id,
        'email', register_user.email,
        'role', register_user.role
    );
END;
$$;

-- 1.3 change_password
CREATE OR REPLACE FUNCTION public.change_password(
    user_id uuid,
    old_password text,
    new_password text
) RETURNS json
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = ''
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = change_password.user_id
          AND password_hash = public.crypt(change_password.old_password, password_hash)
    ) THEN
        RETURN json_build_object('error', 'wrong_password');
    END IF;

    UPDATE public.profiles
    SET password_hash = public.crypt(change_password.new_password, public.gen_salt('bf'))
    WHERE id = change_password.user_id;

    RETURN json_build_object('success', true);
END;
$$;

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
