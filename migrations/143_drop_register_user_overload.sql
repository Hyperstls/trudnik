-- 143: Устранение конфликта перегрузки register_user (PGRST203).
--
-- Миграция 141 создала register_user(text,text,text,text,boolean), но
-- старая (text,text,text,text) осталась → PostgREST не может выбрать
-- кандидата при 4-параметровом вызове (админ-фичи /admin/test-user,
-- admin_users.py) → PGRST203 «Could not choose the best candidate»,
-- создание тестовых пользователей молча не работало.

DROP FUNCTION IF EXISTS public.register_user(text, text, text, text);

-- Гарантия наличия актуальной сигнатуры (идемпотентно).
CREATE OR REPLACE FUNCTION public.register_user(
    p_email text,
    p_password text,
    p_full_name text,
    p_role text DEFAULT 'worker'::text,
    p_worker_visibility boolean DEFAULT true
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE v_user_id uuid;
BEGIN
    IF p_role NOT IN ('worker', 'employer') THEN
        RAISE EXCEPTION 'invalid_role';
    END IF;
    IF EXISTS (SELECT 1 FROM public.profiles WHERE LOWER(email) = LOWER(p_email)) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO public.profiles (id, email, password_hash, full_name, role, email_verified, worker_visibility)
    VALUES (gen_random_uuid(), LOWER(p_email), crypt(p_password, gen_salt('bf', 12)), p_full_name, p_role, FALSE, p_worker_visibility)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.register_user(text, text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.register_user(text, text, text, text, boolean) TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';
