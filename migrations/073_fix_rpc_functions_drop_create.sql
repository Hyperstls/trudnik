-- 073: Пересоздание auth RPC-функций (login_user, register_user, change_password)
-- Проблема: migration 071 пытался сделать CREATE OR REPLACE FUNCTION, меняя
-- return type с TABLE/RETURNS uuid/RETURNS boolean на RETURNS json.
-- PostgreSQL запрещает менять return type через CREATE OR REPLACE.
-- Решение: DROP + CREATE.

BEGIN;

-- ============================================================
-- ШАГ 1: DROP старых функций
-- ============================================================

DROP FUNCTION IF EXISTS public.login_user(text, text) CASCADE;
DROP FUNCTION IF EXISTS public.register_user(text, text, text, text) CASCADE;
DROP FUNCTION IF EXISTS public.change_password(uuid, text, text) CASCADE;

-- ============================================================
-- ШАГ 2: CREATE новых функций с RETURNS json и SET search_path = ''
-- ============================================================

-- 2.1 login_user
CREATE FUNCTION public.login_user(
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

-- 2.2 register_user
CREATE FUNCTION public.register_user(
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

-- 2.3 change_password
CREATE FUNCTION public.change_password(
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
-- ШАГ 3: GRANT EXECUTE на новые функции
-- (дублирование из 071 на случай, если 071 уже применился без CREATE FUNCTION)
-- ============================================================

GRANT EXECUTE ON FUNCTION public.login_user(text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.register_user(text, text, text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.change_password(uuid, text, text) TO anon, authenticated, service_role;

COMMIT;
