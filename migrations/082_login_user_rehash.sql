DROP FUNCTION IF EXISTS login_user(text, text) CASCADE;
CREATE OR REPLACE FUNCTION login_user(p_email text, p_password text)
RETURNS TABLE(user_id uuid, role text, full_name text, email_verified boolean) AS $$
DECLARE
    v_id uuid;
    v_hash text;
    v_role text;
    v_name text;
    v_verified boolean;
BEGIN
    SELECT id, password_hash, role, full_name, email_verified
    INTO v_id, v_hash, v_role, v_name, v_verified
    FROM profiles
    WHERE LOWER(email) = LOWER(p_email)
    LIMIT 1;
    
    IF v_id IS NULL THEN
        RETURN;
    END IF;
    
    IF v_hash IS NULL OR v_hash != crypt(p_password, v_hash) THEN
        RETURN;
    END IF;
    
    -- Пере-хешировать если rounds < 12 (старые хеши $2a$06$ или $2b$06$)
    IF v_hash LIKE '$2a$06$%' OR v_hash LIKE '$2b$06$%' THEN
        UPDATE profiles SET password_hash = crypt(p_password, gen_salt('bf', 12)) WHERE id = v_id;
    END IF;
    
    RETURN QUERY SELECT v_id, v_role, v_name, COALESCE(v_verified, true);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;