CREATE OR REPLACE FUNCTION register_user(
    p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_user_id uuid;
BEGIN
    IF p_role NOT IN ('worker', 'employer') THEN
        RAISE EXCEPTION 'invalid_role';
    END IF;
    IF EXISTS (SELECT 1 FROM public.profiles WHERE LOWER(email) = LOWER(p_email)) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO public.profiles (id, email, password_hash, full_name, role, email_verified)
    VALUES (gen_random_uuid(), LOWER(p_email), crypt(p_password, gen_salt('bf', 12)), p_full_name, p_role, FALSE)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$;

REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;
