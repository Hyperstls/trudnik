-- 149: перегрузка change_password(p_email, p_new_password) для сброса пароля по токену.
--
-- Найдено контрактной проверкой 2026-10-30: app/blueprints/auth.py:586 (сброс пароля)
-- вызывает rpc/change_password с {p_email, p_new_password}, но схема определяла только
-- change_password(p_user_id, p_old_password, p_new_password) (067, 075) — PostgREST
-- отдавал 404, reset-флоу Flask был неработоспособен. Эта миграция добавляет
-- отсутствующую перегрузку (используется и Flask, и djadmin/views_auth.py).
--
-- Семантика: профиль по lower(email); новый хэш crypt(..., gen_salt('bf',12)) — формат
-- $2a$, совместим с python-bcrypt; password_changed_at = now() (инвалидация JWT, B10/B11).
-- Идемпотентно (CREATE OR REPLACE).

CREATE OR REPLACE FUNCTION public.change_password(
    p_email text,
    p_new_password text
) RETURNS boolean
-- rule 04 exception: pgcrypto-зависимая функция — search_path pg_catalog, public
-- (как миграция 130 для register_user/login_user/change_password(uuid,text,text))
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE
    v_user_id uuid;
BEGIN
    SELECT p.id INTO v_user_id FROM public.profiles p
    WHERE lower(p.email) = lower(p_email);
    IF v_user_id IS NULL THEN
        RETURN false;
    END IF;
    UPDATE public.profiles
       SET password_hash = crypt(p_new_password, gen_salt('bf', 12)),
           password_changed_at = now()
     WHERE id = v_user_id;
    RETURN true;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.change_password(text, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.change_password(text, text)
    TO authenticated, service_role, trudnik_dj;
