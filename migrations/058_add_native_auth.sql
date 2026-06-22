-- ============================================
-- Миграция 058: Нативная аутентификация (Amvera)
-- Добавляет email и password_hash в profiles для
-- замены Supabase Auth на нативную PostgreSQL-аутентификацию
-- ============================================

-- Добавить email и password_hash в profiles
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS password_hash text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email) WHERE email IS NOT NULL AND email != '';

-- RPC: логин (проверка пароля через pgcrypto)
CREATE OR REPLACE FUNCTION login_user(p_email text, p_password text)
RETURNS TABLE(user_id uuid, role text, full_name text) AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.role, p.full_name
    FROM profiles p
    WHERE p.email = p_email
      AND p.password_hash = crypt(p_password, p.password_hash)
    LIMIT 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- Права доступа: REVOKE от анонимов, GRANT для authenticated и service_role
-- ============================================

-- RPC: login_user
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

-- RPC: register_user
REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;

-- RPC: change_password
REVOKE EXECUTE ON FUNCTION change_password(uuid, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION change_password(uuid, text, text) TO authenticated, service_role;

-- RPC: регистрация
CREATE OR REPLACE FUNCTION register_user(
    p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'
) RETURNS uuid AS $$
DECLARE
    v_user_id uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM profiles WHERE email = p_email) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO profiles (id, email, password_hash, full_name, role)
    VALUES (gen_random_uuid(), p_email, crypt(p_password, gen_salt('bf')), p_full_name, p_role)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- Права доступа: REVOKE от анонимов, GRANT для authenticated и service_role
-- ============================================

-- RPC: login_user
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

-- RPC: register_user
REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;

-- RPC: change_password
REVOKE EXECUTE ON FUNCTION change_password(uuid, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION change_password(uuid, text, text) TO authenticated, service_role;

-- RPC: смена пароля
CREATE OR REPLACE FUNCTION change_password(
    p_user_id uuid, p_old_password text, p_new_password text
) RETURNS boolean AS $$
DECLARE
    v_hash text;
BEGIN
    SELECT password_hash INTO v_hash FROM profiles WHERE id = p_user_id;
    IF v_hash IS NULL OR v_hash != crypt(p_old_password, v_hash) THEN
        RETURN false;
    END IF;
    UPDATE profiles SET password_hash = crypt(p_new_password, gen_salt('bf')) WHERE id = p_user_id;
    RETURN true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- Права доступа: REVOKE от анонимов, GRANT для authenticated и service_role
-- ============================================

-- RPC: login_user
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

-- RPC: register_user
REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;

-- RPC: change_password
REVOKE EXECUTE ON FUNCTION change_password(uuid, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION change_password(uuid, text, text) TO authenticated, service_role;
