-- РћС‚РѕР·РІР°С‚СЊ EXECUTE РѕС‚ anon РґР»СЏ РїСѓР±Р»РёС‡РЅС‹С… RPC
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;
-- РњРёРіСЂР°С†РёСЏ 077: Р—Р°РјРµРЅРёС‚СЊ РїСЂРѕРІРµСЂРєСѓ role в†’ app_role РІ RLS-РїРѕР»РёС‚РёРєР°С… Рё RPC-С„СѓРЅРєС†РёСЏС…
-- JWT С‚РµРїРµСЂСЊ СЃРѕРґРµСЂР¶РёС‚: role='authenticated' + app_role='worker'/'employer'/'admin'
-- role вЂ” PostgreSQL СЂРѕР»СЊ (authenticated/service_role/trudnikapp)
-- app_role вЂ” РїСЂРёРєР»Р°РґРЅР°СЏ СЂРѕР»СЊ РґР»СЏ RLS-РїСЂРѕРІРµСЂРѕРє (worker/employer/admin)

-- ============================================================================
-- 1. RLS-РїРѕР»РёС‚РёРєРё: admin_skills, admin_religions (skills, religions)
-- ============================================================================

-- skills: admin_skills (Р±С‹Р»Рѕ role IN ('admin', 'trudnikapp') РёР· 073)
DROP POLICY IF EXISTS "admin_skills" ON skills;
CREATE POLICY "admin_skills" ON skills FOR ALL
    USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- religions: admin_religions (Р±С‹Р»Рѕ role IN ('admin', 'trudnikapp') РёР· 073)
DROP POLICY IF EXISTS "admin_religions" ON religions;
CREATE POLICY "admin_religions" ON religions FOR ALL
    USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- ============================================================================
-- 2. RLS-РїРѕР»РёС‚РёРєРё: monetization_settings
-- ============================================================================

-- monetization_settings_insert (Р±С‹Р»Рѕ role IN ('admin', 'trudnikapp') РёР· 073)
DROP POLICY IF EXISTS monetization_settings_insert ON monetization_settings;
CREATE POLICY monetization_settings_insert ON monetization_settings
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- monetization_settings_update (Р±С‹Р»Рѕ role IN ('admin', 'trudnikapp') РёР· 073)
DROP POLICY IF EXISTS monetization_settings_update ON monetization_settings;
CREATE POLICY monetization_settings_update ON monetization_settings
    FOR UPDATE USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- ============================================================================
-- 3. RLS-РїРѕР»РёС‚РёРєРё: receipts
-- ============================================================================

-- receipts_select (Р±С‹Р»Рѕ role = 'admin')
DROP POLICY IF EXISTS receipts_select ON receipts;
CREATE POLICY receipts_select ON receipts
    FOR SELECT USING (
        current_setting('request.jwt.claim.user_id', true)::uuid IN (
            SELECT employer_id FROM _archive_contact_payments
            WHERE _archive_contact_payments.id = receipts.contact_payment_id
            UNION
            SELECT worker_id FROM _archive_contact_payments
            WHERE _archive_contact_payments.id = receipts.contact_payment_id
        )
        OR current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- receipts_insert (Р±С‹Р»Рѕ role = 'admin')
DROP POLICY IF EXISTS receipts_insert ON receipts;
CREATE POLICY receipts_insert ON receipts
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- receipts_update (Р±С‹Р»Рѕ role = 'admin')
DROP POLICY IF EXISTS receipts_update ON receipts;
CREATE POLICY receipts_update ON receipts
    FOR UPDATE USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- ============================================================================
-- 4. RLS-РїРѕР»РёС‚РёРєРё: audit_log (admin read)
-- ============================================================================
DROP POLICY IF EXISTS "Admins can read audit_log" ON audit_log;
CREATE POLICY "Admins can read audit_log" ON audit_log
    FOR SELECT USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- ============================================================================
-- 5. RLS-РїРѕР»РёС‚РёРєРё: notifications (admin delete)
-- ============================================================================
DROP POLICY IF EXISTS "Admins can delete notifications" ON notifications;
CREATE POLICY "Admins can delete notifications" ON notifications
    FOR DELETE USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- ============================================================================
-- 6. RPC-С„СѓРЅРєС†РёРё SECURITY DEFINER: Р·Р°РјРµРЅР° role в†’ app_role РґР»СЏ РїСЂРѕРІРµСЂРєРё admin
--    (service_role Рё trudnikapp РѕСЃС‚Р°СЋС‚СЃСЏ РєР°Рє PostgreSQL-СЂРѕР»Рё С‡РµСЂРµР· request.jwt.claim.role)
-- ============================================================================

-- 6a. accept_application (M8 РёР· 075)
DROP FUNCTION IF EXISTS public.accept_application(uuid, uuid);
CREATE OR REPLACE FUNCTION public.accept_application(p_job_id uuid, p_app_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_current_workers int; v_max_workers int; v_job_status text;
    v_new_count int; v_new_status text; v_employer_id uuid;
BEGIN
    SELECT current_workers, max_workers, status, employer_id
      INTO v_current_workers, v_max_workers, v_job_status, v_employer_id
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ');
    END IF;

    -- РџСЂРѕРІРµСЂРєР° РІР»Р°РґРµР»СЊС†Р°: С‚РѕР»СЊРєРѕ employer_id Р·Р°РґР°РЅРёСЏ РёР»Рё admin/service_role
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ Р·Р°РєСЂС‹С‚Рѕ РґР»СЏ РїСЂРёРЅСЏС‚РёСЏ');
    END IF;
    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Р’СЃРµ РјРµСЃС‚Р° Р·Р°РЅСЏС‚С‹');
    END IF;

    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE public.jobs SET status = v_new_status, current_workers = v_new_count
    WHERE id = p_job_id;

    UPDATE public.applications SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status IN ('pending', 'rejected');

    IF NOT FOUND THEN
        UPDATE public.jobs SET status = v_job_status, current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'РћС‚РєР»РёРє РЅРµ РЅР°Р№РґРµРЅ РёР»Рё СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅ');
    END IF;

    UPDATE public.applications SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    RETURN json_build_object('success', true, 'current_workers', v_new_count, 'job_status', v_new_status);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

-- 6b. reject_application (M9 РёР· 075)
DROP FUNCTION IF EXISTS public.reject_application(uuid, uuid);
CREATE OR REPLACE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_current_status text; v_current_workers int; v_max_workers int;
    v_job_status text; v_employer_id uuid;
    v_new_workers int; v_new_job_status text; v_result json;
BEGIN
    -- РџСЂРѕРІРµСЂРєР° РІР»Р°РґРµР»СЊС†Р°: employer_id Р·Р°РґР°РЅРёСЏ РёР»Рё admin/service_role
    SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ');
    END IF;
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    SELECT status INTO v_current_status
    FROM public.applications
    WHERE id = p_app_id AND job_id = p_job_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'РћС‚РєР»РёРє РЅРµ РЅР°Р№РґРµРЅ');
    END IF;

    IF v_current_status = 'rejected' THEN
        RETURN json_build_object('success', false, 'error', 'РћС‚РєР»РёРє СѓР¶Рµ РѕС‚РєР»РѕРЅС‘РЅ');
    END IF;

    UPDATE public.applications SET status = 'rejected'
    WHERE id = p_app_id AND job_id = p_job_id;

    IF v_current_status = 'accepted' THEN
        SELECT current_workers, max_workers, status
          INTO v_current_workers, v_max_workers, v_job_status
          FROM public.jobs WHERE id = p_job_id;

        v_new_workers := GREATEST(v_current_workers - 1, 0);
        v_new_job_status := CASE WHEN v_new_workers = 0 THEN 'open' ELSE v_job_status END;

        UPDATE public.jobs
        SET status = v_new_job_status, current_workers = v_new_workers
        WHERE id = p_job_id;
    END IF;

    RETURN json_build_object('success', true);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.reject_application(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;

-- 6c. restore_job_atomic (M14 РёР· 075)
DROP FUNCTION IF EXISTS public.restore_job_atomic(uuid, uuid);
CREATE OR REPLACE FUNCTION public.restore_job_atomic(p_job_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_cancelled_count int;
BEGIN
    SELECT employer_id, status INTO v_employer_id, v_status
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ', 'code', 'job_not_found');
    END IF;

    IF v_employer_id != p_user_id
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    -- РЎР±СЂРѕСЃ СЃС‚Р°С‚СѓСЃР° Р·Р°РґР°РЅРёСЏ
    UPDATE public.jobs SET status = 'open', current_workers = 0, updated_at = now()
    WHERE id = p_job_id;

    -- РћС‚РјРµРЅР° РїСЂРёРЅСЏС‚С‹С… Р·Р°СЏРІРѕРє
    WITH cancelled AS (
        UPDATE public.applications SET status = 'cancelled'
        WHERE job_id = p_job_id AND status = 'accepted'
        RETURNING id
    )
    SELECT count(*) INTO v_cancelled_count FROM cancelled;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Р—Р°РґР°РЅРёРµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРѕ',
        'job_status', 'open',
        'current_workers', 0,
        'cancelled_applications', v_cancelled_count
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) TO authenticated, service_role;

-- 6d. delete_job_cascade (M16 РёР· 075)
DROP FUNCTION IF EXISTS public.delete_job_cascade(uuid);
CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS json
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_deleted_apps int;
    v_deleted_skills int;
    v_deleted_photos int;
    v_deleted_favorites int;
    v_deleted_invitations int;
    v_deleted_notifications int;
BEGIN
    SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ');
    END IF;

    -- РџСЂРѕРІРµСЂРєР° РІР»Р°РґРµР»СЊС†Р°
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    DELETE FROM public.applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM public.job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM public.job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM public.favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM public.invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    DELETE FROM public.notifications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    DELETE FROM public.jobs WHERE id = p_job_id;

    RETURN json_build_object(
        'success', true,
        'deleted_applications', v_deleted_apps,
        'deleted_skills', v_deleted_skills,
        'deleted_photos', v_deleted_photos,
        'deleted_favorites', v_deleted_favorites,
        'deleted_invitations', v_deleted_invitations,
        'deleted_notifications', v_deleted_notifications
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;

-- ============================================================================
-- 7. RLS-РїРѕР»РёС‚РёРєРё: notifications Рё email_log вЂ” INSERT С‚РѕР»СЊРєРѕ service_role
--    (СЌС‚Рё РїСЂРѕРІРµСЂСЏСЋС‚ role, Р° РЅРµ app_role вЂ” РѕСЃС‚Р°РІР»СЏРµРј РєР°Рє РµСЃС‚СЊ, С‚.Рє. service_role
--     СЌС‚Рѕ PostgreSQL-СЂРѕР»СЊ, Р° РЅРµ РїСЂРёРєР»Р°РґРЅР°СЏ)
--    РќРћ: РґРѕР±Р°РІР»СЏРµРј РїСЂРѕРІРµСЂРєСѓ app_role = 'admin' РґР»СЏ СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
-- ============================================================================

DROP POLICY IF EXISTS "Service can insert notifications" ON notifications;
CREATE POLICY "Service can insert notifications" ON notifications
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.role', true) = 'service_role'
        OR current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

DROP POLICY IF EXISTS "Service can insert email logs" ON email_log;
CREATE POLICY "Service can insert email logs" ON email_log
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.role', true) = 'service_role'
        OR current_setting('request.jwt.claim.app_role', true) = 'admin'
    );
-- РњРёРіСЂР°С†РёСЏ 077b: Р”Р°С‚СЊ trudnik Рё trudnikapp РЅР°СЃР»РµРґРѕРІР°РЅРёРµ service_role
-- РќРµРѕР±С…РѕРґРёРјРѕ РґР»СЏ С‚РѕРіРѕ, С‡С‚РѕР±С‹ SET ROLE service_role СЂР°Р±РѕС‚Р°Р» С‡РµСЂРµР· PostgREST
-- service_role РЅСѓР¶РµРЅ РґР»СЏ РѕР±С…РѕРґР° RLS РІ admin-Р·Р°РїСЂРѕСЃР°С… (postgrest_admin_request)

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnik') THEN
        GRANT anon, authenticated, service_role TO trudnik;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnikapp') THEN
        GRANT anon, authenticated, service_role TO trudnikapp;
    END IF;
END $$;
-- Migration 078: Drop exec_sql RPC
-- Security: exec_sql(text) allowed arbitrary SQL execution.
-- Anyone with PGRST_JWT_SECRET had root access to the database.
-- Replaced by CLI-only psycopg2 connections in scripts.

DROP FUNCTION IF EXISTS public.exec_sql(text) CASCADE;
REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM service_role;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT TRUE;
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
-- РџРµСЂРµРЅРµСЃС‚Рё Р·Р°РІРёСЃРёРјРѕСЃС‚Рё СЃ РґСѓР±Р»РёРєР°С‚РѕРІ РЅР° "РІС‹Р¶РёРІС€РёРµ" РїСЂРѕС„РёР»Рё
DO $$
DECLARE
    dup RECORD;
    keep_id uuid;
BEGIN
    FOR dup IN
        SELECT LOWER(email) AS le, MIN(id) AS keep_id
        FROM profiles GROUP BY LOWER(email) HAVING COUNT(*) > 1
    LOOP
        keep_id := dup.keep_id;
        
        UPDATE applications SET worker_id = keep_id
        WHERE worker_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE jobs SET employer_id = keep_id
        WHERE employer_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE ratings SET rater_user_id = keep_id
        WHERE rater_user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE ratings SET rated_user_id = keep_id
        WHERE rated_user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE notifications SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE favorites SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE favorites SET target_id = keep_id
        WHERE target_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE blacklists SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE blacklists SET blocked_user_id = keep_id
        WHERE blocked_user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE messages SET sender_id = keep_id
        WHERE sender_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE push_subscriptions SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE user_skills SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE invitations SET employer_id = keep_id
        WHERE employer_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE invitations SET worker_id = keep_id
        WHERE worker_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE audit_log SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        -- РЈРґР°Р»РёС‚СЊ РґСѓР±Р»РёРєР°С‚С‹
        DELETE FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id;
    END LOOP;
END $$;

-- РџСЂРёРІРµСЃС‚Рё Рє РЅРёР¶РЅРµРјСѓ СЂРµРіРёСЃС‚СЂСѓ
UPDATE profiles SET email = LOWER(email) WHERE email != LOWER(email);

-- Case-insensitive РёРЅРґРµРєСЃ
DROP INDEX IF EXISTS idx_profiles_email;
CREATE UNIQUE INDEX idx_profiles_email ON profiles(LOWER(email));
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
    
    -- РџРµСЂРµ-С…РµС€РёСЂРѕРІР°С‚СЊ РµСЃР»Рё rounds < 12 (СЃС‚Р°СЂС‹Рµ С…РµС€Рё $2a$06$ РёР»Рё $2b$06$)
    IF v_hash LIKE '$2a$06$%' OR v_hash LIKE '$2b$06$%' THEN
        UPDATE profiles SET password_hash = crypt(p_password, gen_salt('bf', 12)) WHERE id = v_id;
    END IF;
    
    RETURN QUERY SELECT v_id, v_role, v_name, COALESCE(v_verified, true);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;
ALTER TABLE notification_outbox ADD COLUMN IF NOT EXISTS attempts INT DEFAULT 0;
ALTER TABLE notification_outbox DROP CONSTRAINT IF EXISTS notification_outbox_status_check;
ALTER TABLE notification_outbox ADD CONSTRAINT notification_outbox_status_check 
    CHECK (status IN ('pending','sent','failed','skipped'));
CREATE OR REPLACE FUNCTION public.withdraw_application_atomic(
    p_application_id uuid, p_user_id uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_worker_id uuid;
    v_job_id uuid;
    v_status text;
    v_job_status text;
    v_current_workers int;
    v_max_workers int;
    v_date_time timestamptz;
    v_hours_before float8;
    v_employer_id uuid;
BEGIN
    SELECT worker_id, job_id, status
    INTO v_worker_id, v_job_id, v_status
    FROM public.applications
    WHERE id = p_application_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°СЏРІРєР° РЅРµ РЅР°Р№РґРµРЅР°', 'code', 'application_not_found');
    END IF;

    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р’С‹ РЅРµ Р°РІС‚РѕСЂ СЌС‚РѕР№ Р·Р°СЏРІРєРё', 'code', 'not_owner');
    END IF;

    IF v_status = 'withdrawn' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°СЏРІРєР° СѓР¶Рµ РѕС‚РѕР·РІР°РЅР°', 'code', 'already_withdrawn');
    END IF;

    IF v_status = 'accepted' THEN
        -- РџСЂРѕРІРµСЂРєР° 12-С‡Р°СЃРѕРІРѕРіРѕ РѕРєРЅР°
        SELECT status, current_workers, max_workers, date_time, employer_id
        INTO v_job_status, v_current_workers, v_max_workers, v_date_time, v_employer_id
        FROM public.jobs
        WHERE id = v_job_id
        FOR UPDATE;

        IF v_date_time IS NOT NULL THEN
            v_hours_before := EXTRACT(EPOCH FROM (v_date_time - now())) / 3600.0;
            IF v_hours_before < 12 THEN
                RETURN jsonb_build_object(
                    'success', false,
                    'error', format('РќРµР»СЊР·СЏ РѕС‚РѕР·РІР°С‚СЊ РјРµРЅРµРµ С‡РµРј Р·Р° 12 С‡Р°СЃРѕРІ РґРѕ РЅР°С‡Р°Р»Р° (РѕСЃС‚Р°Р»РѕСЃСЊ %.1f С‡)', v_hours_before),
                    'code', 'too_close_to_start'
                );
            END IF;
        END IF;

        -- РЈРјРµРЅСЊС€РёС‚СЊ current_workers, РІРѕР·РјРѕР¶РЅРѕ РІРµСЂРЅСѓС‚СЊ СЃС‚Р°С‚СѓСЃ РІ open
        v_current_workers := GREATEST(0, v_current_workers - 1);
        IF v_current_workers = 0 AND v_job_status = 'completed' THEN
            v_job_status := 'open';
        END IF;

        UPDATE public.jobs
        SET current_workers = v_current_workers, status = v_job_status, updated_at = now()
        WHERE id = v_job_id;
    ELSE
        -- Р”Р»СЏ pending вЂ” РїРѕР»СѓС‡РёС‚СЊ employer_id РґР»СЏ СѓРІРµРґРѕРјР»РµРЅРёСЏ
        SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = v_job_id;
    END IF;

    IF v_employer_id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ', 'code', 'job_not_found'
        );
    END IF;

    UPDATE public.applications
    SET status = 'withdrawn'
    WHERE id = p_application_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Р—Р°СЏРІРєР° РѕС‚РѕР·РІР°РЅР°',
        'new_status', 'withdrawn',
        'job_id', v_job_id,
        'employer_id', v_employer_id
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) TO authenticated, service_role;
-- ============================================================================
-- РњРёРіСЂР°С†РёСЏ 085: РСЃРїСЂР°РІРёС‚СЊ restore_job_atomic
-- РџСЂРѕР±Р»РµРјР°: UPDATE applications SET status = 'cancelled' РЅР°СЂСѓС€Р°Р» CHECK-constraint,
-- С‚.Рє. РґРѕРїСѓСЃС‚РёРјС‹Рµ СЃС‚Р°С‚СѓСЃС‹: ('pending', 'accepted', 'rejected', 'withdrawn')
-- Р РµС€РµРЅРёРµ: rejected в†’ pending (РЅРµ cancelled!)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.restore_job_atomic(p_job_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_restored_count int;
    v_restored_worker_ids uuid[];
BEGIN
    SELECT employer_id, status INTO v_employer_id, v_status
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ', 'code', 'job_not_found');
    END IF;

    IF v_employer_id != p_user_id
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin') THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    IF v_status != 'cancelled' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('РњРѕР¶РЅРѕ РІРѕСЃСЃС‚Р°РЅРѕРІРёС‚СЊ С‚РѕР»СЊРєРѕ РѕС‚РјРµРЅС‘РЅРЅРѕРµ Р·Р°РґР°РЅРёРµ (С‚РµРєСѓС‰РёР№ СЃС‚Р°С‚СѓСЃ: %s)', v_status),
            'code', 'not_cancelled'
        );
    END IF;

    UPDATE public.jobs
    SET status = 'open', current_workers = 0, updated_at = now()
    WHERE id = p_job_id;

    -- РњРµРЅСЏРµРј rejected Р·Р°СЏРІРєРё РЅР° pending (РќР• cancelled вЂ” СЌС‚Рѕ РЅР°СЂСѓС€Р°РµС‚ CHECK!)
    WITH restored AS (
        UPDATE public.applications SET status = 'pending'
        WHERE job_id = p_job_id AND status = 'rejected'
        RETURNING id, worker_id
    )
    SELECT count(*), array_agg(DISTINCT worker_id)
    INTO v_restored_count, v_restored_worker_ids
    FROM restored;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Р—Р°РґР°РЅРёРµ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅРѕ',
        'job_status', 'open',
        'current_workers', 0,
        'restored_applications', v_restored_count,
        'restored_worker_ids', COALESCE(to_jsonb(v_restored_worker_ids), '[]'::jsonb)
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) TO authenticated, service_role;
-- ============================================================================
-- РњРёРіСЂР°С†РёСЏ 086: РСЃРїСЂР°РІРёС‚СЊ delete_job_cascade вЂ” РіР°СЂР°РЅС‚РёСЂРѕРІР°С‚СЊ СѓРґР°Р»РµРЅРёРµ С‡РµСЂРµР· FK
-- РџСЂРѕР±Р»РµРјР°: РІ СЂР°РЅРЅРёС… РІРµСЂСЃРёСЏС… РёСЃРїРѕР»СЊР·РѕРІР°Р»СЃСЏ ILIKE '%uuid%' РґР»СЏ РїРѕРёСЃРєР° СѓРІРµРґРѕРјР»РµРЅРёР№,
-- С‡С‚Рѕ РЅРµРЅР°РґС‘Р¶РЅРѕ Рё РјРµРґР»РµРЅРЅРѕ. РўР°Р±Р»РёС†Р° notifications РёРјРµРµС‚ РєРѕР»РѕРЅРєСѓ job_id (FK),
-- РїРѕСЌС‚РѕРјСѓ РёСЃРїРѕР»СЊР·СѓРµРј DELETE WHERE job_id = p_job_id.
-- РўР°РєР¶Рµ СѓРґР°Р»СЏРµРј orphaned-СѓРІРµРґРѕРјР»РµРЅРёСЏ С‡РµСЂРµР· ILIKE (РѕСЃС‚Р°РІР»РµРЅРѕ РєР°Рє СЃС‚СЂР°С…РѕРІРєР°).
-- ============================================================================
CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS json
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_deleted_apps int;
    v_deleted_skills int;
    v_deleted_photos int;
    v_deleted_favorites int;
    v_deleted_invitations int;
    v_deleted_notifications int;
BEGIN
    SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ');
    END IF;

    -- РџСЂРѕРІРµСЂРєР° РІР»Р°РґРµР»СЊС†Р° (РґР»СЏ РІС‹Р·РѕРІРѕРІ РѕС‚ РёРјРµРЅРё РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ)
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    DELETE FROM public.applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM public.job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM public.job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM public.favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM public.invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    -- РћСЃРЅРѕРІРЅРѕРµ РёСЃРїСЂР°РІР»РµРЅРёРµ: РёСЃРїРѕР»СЊР·СѓРµРј FK-РєРѕР»РѕРЅРєСѓ job_id РІРјРµСЃС‚Рѕ ILIKE '%uuid%'
    DELETE FROM public.notifications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    -- РЎС‚СЂР°С…РѕРІРєР°: СѓРґР°Р»РёС‚СЊ orphaned-СѓРІРµРґРѕРјР»РµРЅРёСЏ, РіРґРµ job_id IS NULL,
    -- РЅРѕ UUID Р·Р°РґР°РЅРёСЏ РІСЃС‚СЂРµС‡Р°РµС‚СЃСЏ РІ С‚РµРєСЃС‚Рµ (СѓСЃС‚Р°СЂРµРІС€РёРµ Р·Р°РїРёСЃРё)
    DELETE FROM public.notifications
    WHERE job_id IS NULL
      AND message ILIKE '%' || p_job_id::text || '%';

    DELETE FROM public.jobs WHERE id = p_job_id;

    RETURN json_build_object(
        'success', true,
        'deleted_applications', v_deleted_apps,
        'deleted_skills', v_deleted_skills,
        'deleted_photos', v_deleted_photos,
        'deleted_favorites', v_deleted_favorites,
        'deleted_invitations', v_deleted_invitations,
        'deleted_notifications', v_deleted_notifications
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;
-- ============================================================================
-- РњРёРіСЂР°С†РёСЏ 088: Р”РѕР±Р°РІРёС‚СЊ РїСЂРѕРІРµСЂРєСѓ expires_at РІ apply_job_atomic
-- РџСЂРѕР±Р»РµРјР°: apply_job_atomic РЅРµ РїСЂРѕРІРµСЂСЏР»Р° expires_at, РїРѕСЌС‚РѕРјСѓ СЂР°Р±РѕС‚РЅРёРєРё
-- РјРѕРіР»Рё РѕС‚РєР»РёРєР°С‚СЊСЃСЏ РЅР° Р·Р°РґР°РЅРёСЏ СЃ РёСЃС‚С‘РєС€РёРј СЃСЂРѕРєРѕРј.
-- Р РµС€РµРЅРёРµ: РґРѕР±Р°РІРёС‚СЊ РїСЂРѕРІРµСЂРєСѓ v_expires_at < now() РїРµСЂРµРґ СЃРѕР·РґР°РЅРёРµРј РѕС‚РєР»РёРєР°.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.apply_job_atomic(
    p_job_id uuid, p_worker_id uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_max_workers int;
    v_current_workers int;
    v_status text;
    v_employer_id uuid;
    v_expires_at timestamptz;
    v_app_id uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id, expires_at
      INTO v_max_workers, v_current_workers, v_status, v_employer_id, v_expires_at
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ', 'code', 'job_not_found');
    END IF;

    IF v_status NOT IN ('open', 'active') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµРґРѕСЃС‚СѓРїРЅРѕ РґР»СЏ РѕС‚РєР»РёРєР°', 'code', 'job_not_open');
    END IF;

    -- РџСЂРѕРІРµСЂРєР° СЃСЂРѕРєР° РґРµР№СЃС‚РІРёСЏ Р·Р°РґР°РЅРёСЏ
    IF v_expires_at IS NOT NULL AND v_expires_at < now() THEN
        RETURN jsonb_build_object('success', false, 'error', 'РЎСЂРѕРє СЂР°Р·РјРµС‰РµРЅРёСЏ Р·Р°РґР°РЅРёСЏ РёСЃС‚С‘Рє', 'code', 'job_expired');
    END IF;

    IF v_employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'own job', 'code', 'own_job');
    END IF;

    IF EXISTS (SELECT 1 FROM public.blacklists
               WHERE user_id = v_employer_id AND blocked_user_id = p_worker_id) THEN
        RETURN jsonb_build_object('success', false, 'error', 'blacklisted', 'code', 'blacklisted');
    END IF;

    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (p_job_id, p_worker_id, 'pending')
    RETURNING id INTO v_app_id;

    RETURN jsonb_build_object('success', true, 'application_id', v_app_id, 'employer_id', v_employer_id);
EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('success', false, 'error', 'duplicate', 'code', 'duplicate');
END;
$$;

REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;
-- ============================================================================
-- РњРёРіСЂР°С†РёСЏ 089: РџРµСЂРµРЅРµСЃС‚Рё profiles.skills в†’ user_skills Рё СѓРґР°Р»РёС‚СЊ РєРѕР»РѕРЅРєСѓ
-- РџСЂРѕР±Р»РµРјР°: РќР°РІС‹РєРё РґСѓР±Р»РёСЂСѓСЋС‚СЃСЏ вЂ” РјР°СЃСЃРёРІ text[] РІ profiles.skills Рё С‚Р°Р±Р»РёС†Р° user_skills.
-- Р РµС€РµРЅРёРµ: РџРµСЂРµРЅРѕСЃ РґР°РЅРЅС‹С… РІ user_skills, Р·Р°С‚РµРј DROP COLUMN profiles.skills.
-- ============================================================================

-- РЁР°Рі 1: РџРµСЂРµРЅРµСЃС‚Рё СЃСѓС‰РµСЃС‚РІСѓСЋС‰РёРµ РЅР°РІС‹РєРё РёР· profiles.skills (text[]) РІ user_skills
-- Р”Р»СЏ РєР°Р¶РґРѕРіРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ СЃ РЅРµРїСѓСЃС‚С‹Рј skills РЅР°С…РѕРґРёРј skill_id РїРѕ РёРјРµРЅРё
DO $$
DECLARE
    v_rec RECORD;
    v_skill_name text;
    v_skill_id uuid;
BEGIN
    FOR v_rec IN
        SELECT id, unnest(skills) AS skill_name
        FROM public.profiles
        WHERE skills IS NOT NULL AND array_length(skills, 1) > 0
    LOOP
        -- РќРѕСЂРјР°Р»РёР·СѓРµРј РёРјСЏ РЅР°РІС‹РєР°
        v_skill_name := trim(both ' "' FROM v_rec.skill_name);
        IF v_skill_name = '' THEN
            CONTINUE;
        END IF;

        -- РС‰РµРј skill_id РїРѕ РёРјРµРЅРё (РёРіРЅРѕСЂРёСЂСѓСЏ СЂРµРіРёСЃС‚СЂ)
        SELECT id INTO v_skill_id
        FROM public.skills
        WHERE LOWER(name) = LOWER(v_skill_name)
        LIMIT 1;

        -- Р•СЃР»Рё РЅР°РІС‹Рє РЅРµ РЅР°Р№РґРµРЅ РІ СЃРїСЂР°РІРѕС‡РЅРёРєРµ вЂ” СЃРѕР·РґР°С‘Рј
        IF v_skill_id IS NULL THEN
            INSERT INTO public.skills (name) VALUES (v_skill_name)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id INTO v_skill_id;
            IF v_skill_id IS NULL THEN
                SELECT id INTO v_skill_id FROM public.skills
                WHERE LOWER(name) = LOWER(v_skill_name)
                LIMIT 1;
            END IF;
        END IF;

        -- Р’СЃС‚Р°РІР»СЏРµРј СЃРІСЏР·СЊ user-skill (РїСЂРѕРїСѓСЃРєР°РµРј РґСѓР±Р»РёРєР°С‚С‹)
        IF v_skill_id IS NOT NULL THEN
            INSERT INTO public.user_skills (user_id, skill_id)
            VALUES (v_rec.id, v_skill_id)
            ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;
END $$;

-- РЁР°Рі 2: РЈРґР°Р»РёС‚СЊ РєРѕР»РѕРЅРєСѓ skills РёР· profiles
ALTER TABLE public.profiles DROP COLUMN IF EXISTS skills;
-- 090_admin_dashboard_rpc.sql
-- Р—Р°РјРµРЅР° 9 РѕС‚РґРµР»СЊРЅС‹С… count-Р·Р°РїСЂРѕСЃРѕРІ РЅР° РѕРґРёРЅ RPC-РІС‹Р·РѕРІ РґР»СЏ Р°РґРјРёРЅ-РґР°С€Р±РѕСЂРґР°.
-- РЈСЃС‚СЂР°РЅСЏРµС‚ N+1 РїСЂРѕР±Р»РµРјСѓ: РІРјРµСЃС‚Рѕ 9 HTTP-Р·Р°РїСЂРѕСЃРѕРІ в†’ 1 RPC.

CREATE OR REPLACE FUNCTION get_admin_dashboard_stats()
RETURNS JSON AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'total_users', (SELECT COUNT(*) FROM profiles),
        'workers', (SELECT COUNT(*) FROM profiles WHERE role='worker'),
        'employers', (SELECT COUNT(*) FROM profiles WHERE role='employer'),
        'admins', (SELECT COUNT(*) FROM profiles WHERE role='admin'),
        'total_jobs', (SELECT COUNT(*) FROM jobs),
        'open_jobs', (SELECT COUNT(*) FROM jobs WHERE status='open'),
        'completed_jobs', (SELECT COUNT(*) FROM jobs WHERE status='completed'),
        'cancelled_jobs', (SELECT COUNT(*) FROM jobs WHERE status='cancelled'),
        'pending_verifications', (SELECT COUNT(*) FROM profiles WHERE verification_status='pending')
    ) INTO result;
    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

GRANT EXECUTE ON FUNCTION get_admin_dashboard_stats() TO service_role;
-- 091_unify_rpc_jsonb.sql
-- РЈРЅРёС„РёРєР°С†РёСЏ return type: Р·Р°РјРµРЅР° RETURNS json в†’ RETURNS jsonb РґР»СЏ 5 RPC-С„СѓРЅРєС†РёР№.
-- jsonb вЂ” РЅР°С‚РёРІРЅС‹Р№ С‚РёРї PostgreSQL, СЌС„С„РµРєС‚РёРІРЅРµРµ РґР»СЏ С…СЂР°РЅРµРЅРёСЏ Рё РѕР±СЂР°Р±РѕС‚РєРё.
-- Р›РѕРіРёРєР° С„СѓРЅРєС†РёР№ РќР• РјРµРЅСЏРµС‚СЃСЏ, С‚РѕР»СЊРєРѕ С‚РёРї РІРѕР·РІСЂР°С‚Р° Рё json_build_object в†’ jsonb_build_object.

-- 1. accept_application
DROP FUNCTION IF EXISTS accept_application(uuid, uuid);
CREATE OR REPLACE FUNCTION accept_application(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_job_id uuid;
    v_worker_id uuid;
    v_employer_id uuid;
    v_status text;
    v_current_workers int;
    v_max_workers int;
BEGIN
    SELECT a.job_id, a.worker_id, j.employer_id, a.status
    INTO v_job_id, v_worker_id, v_employer_id, v_status
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    WHERE a.id = p_application_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'РћС‚РєР»РёРє РЅРµ РЅР°Р№РґРµРЅ', 'code', 'not_found');
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'РќРµС‚ РґРѕСЃС‚СѓРїР°', 'code', 'forbidden');
    END IF;

    IF v_status != 'pending' THEN
        RETURN jsonb_build_object('success', false, 'error', 'РћС‚РєР»РёРє СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅ', 'code', 'invalid_status');
    END IF;

    SELECT j.current_workers, j.max_workers
    INTO v_current_workers, v_max_workers
    FROM jobs j WHERE j.id = v_job_id;

    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'РќРµС‚ СЃРІРѕР±РѕРґРЅС‹С… РјРµСЃС‚', 'code', 'no_slots');
    END IF;

    UPDATE applications SET status = 'accepted', updated_at = NOW()
    WHERE id = p_application_id AND status = 'pending';

    UPDATE jobs
    SET current_workers = current_workers + 1,
        status = CASE WHEN current_workers + 1 >= max_workers THEN 'completed' ELSE 'open' END,
        updated_at = NOW()
    WHERE id = v_job_id
    RETURNING status INTO v_status;

    RETURN jsonb_build_object(
        'success', true,
        'new_status', v_status,
        'worker_id', v_worker_id,
        'job_id', v_job_id
    );
END;
$$;

-- 2. reject_application
DROP FUNCTION IF EXISTS reject_application(uuid, uuid);
CREATE OR REPLACE FUNCTION reject_application(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_job_id uuid;
    v_worker_id uuid;
    v_employer_id uuid;
    v_status text;
BEGIN
    SELECT a.job_id, a.worker_id, j.employer_id, a.status
    INTO v_job_id, v_worker_id, v_employer_id, v_status
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    WHERE a.id = p_application_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'РћС‚РєР»РёРє РЅРµ РЅР°Р№РґРµРЅ', 'code', 'not_found');
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'РќРµС‚ РґРѕСЃС‚СѓРїР°', 'code', 'forbidden');
    END IF;

    IF v_status NOT IN ('pending', 'accepted') THEN
        RETURN jsonb_build_object('success', false, 'error', 'РћС‚РєР»РёРє СѓР¶Рµ РѕР±СЂР°Р±РѕС‚Р°РЅ', 'code', 'invalid_status');
    END IF;

    IF v_status = 'accepted' THEN
        UPDATE jobs
        SET current_workers = GREATEST(current_workers - 1, 0),
            status = CASE WHEN current_workers - 1 < max_workers THEN 'open' ELSE status END,
            updated_at = NOW()
        WHERE id = v_job_id;
    END IF;

    UPDATE applications SET status = 'rejected', updated_at = NOW()
    WHERE id = p_application_id;

    RETURN jsonb_build_object(
        'success', true,
        'worker_id', v_worker_id,
        'job_id', v_job_id
    );
END;
$$;

-- 3. delete_job_cascade
DROP FUNCTION IF EXISTS delete_job_cascade(uuid);
CREATE OR REPLACE FUNCTION delete_job_cascade(p_job_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM applications WHERE job_id = p_job_id;
    DELETE FROM job_favorites WHERE job_id = p_job_id;
    DELETE FROM job_payments WHERE job_id = p_job_id;
    DELETE FROM invitations WHERE job_id = p_job_id;
    DELETE FROM jobs WHERE id = p_job_id;
    RETURN jsonb_build_object('success', true, 'deleted_job_id', p_job_id);
END;
$$;

-- 4. delete_user_cascade (Р»РѕРіРёРєР° СЂР°СЃС€РёСЂРµРЅР° РІ 092)
DROP FUNCTION IF EXISTS delete_user_cascade(uuid);
CREATE OR REPLACE FUNCTION delete_user_cascade(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_role text;
    v_job_id uuid;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ', 'code', 'not_found');
    END IF;

    IF v_role = 'employer' THEN
        FOR v_job_id IN SELECT id FROM jobs WHERE employer_id = p_user_id LOOP
            PERFORM delete_job_cascade(v_job_id);
        END LOOP;
    END IF;

    DELETE FROM applications WHERE worker_id = p_user_id;
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM notification_outbox WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE user_id = p_user_id OR employer_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE user_id = p_user_id OR blocked_user_id = p_user_id;
    DELETE FROM ratings WHERE rater_id = p_user_id OR rated_user_id = p_user_id;
    DELETE FROM invitations WHERE employer_id = p_user_id OR worker_id = p_user_id;
    DELETE FROM user_skills WHERE user_id = p_user_id;
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;
    DELETE FROM messages WHERE sender_id = p_user_id OR receiver_id = p_user_id;
    DELETE FROM job_payments WHERE payer_id = p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id = p_user_id;

    UPDATE audit_log SET user_id = NULL WHERE user_id = p_user_id;

    DELETE FROM profiles WHERE id = p_user_id;

    RETURN jsonb_build_object('success', true, 'deleted_user_id', p_user_id, 'role', v_role);
END;
$$;

-- 5. apply_job_atomic
DROP FUNCTION IF EXISTS apply_job_atomic(uuid, uuid);
CREATE OR REPLACE FUNCTION apply_job_atomic(p_job_id uuid, p_worker_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_job jobs%ROWTYPE;
    v_existing_id uuid;
    v_blacklisted boolean;
    v_worker_role text;
BEGIN
    SELECT role INTO v_worker_role FROM profiles WHERE id = p_worker_id;
    IF v_worker_role IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ', 'code', 'user_not_found');
    END IF;
    IF v_worker_role != 'worker' THEN
        RETURN jsonb_build_object('success', false, 'error', 'РўРѕР»СЊРєРѕ СЂР°Р±РѕС‚РЅРёРєРё РјРѕРіСѓС‚ РѕС‚РєР»РёРєР°С‚СЊСЃСЏ', 'code', 'not_worker');
    END IF;

    SELECT * INTO v_job FROM jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р—Р°РґР°РЅРёРµ РЅРµ РЅР°Р№РґРµРЅРѕ', 'code', 'job_not_found');
    END IF;

    IF v_job.status != 'open' THEN
        RETURN jsonb_build_object('success', false, 'error', 'РќР° СЌС‚Рѕ Р·Р°РґР°РЅРёРµ РЅРµР»СЊР·СЏ РѕС‚РєР»РёРєР°С‚СЊСЃСЏ', 'code', 'job_not_open');
    END IF;

    IF v_job.employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'РќРµР»СЊР·СЏ РѕС‚РєР»РёРєР°С‚СЊСЃСЏ РЅР° СЃРІРѕС‘ Р·Р°РґР°РЅРёРµ', 'code', 'own_job');
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM blacklists
        WHERE user_id = v_job.employer_id AND blocked_user_id = p_worker_id
    ) INTO v_blacklisted;
    IF v_blacklisted THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р Р°Р±РѕС‚РѕРґР°С‚РµР»СЊ РґРѕР±Р°РІРёР» РІР°СЃ РІ С‡С‘СЂРЅС‹Р№ СЃРїРёСЃРѕРє', 'code', 'blacklisted');
    END IF;

    SELECT id INTO v_existing_id FROM applications
    WHERE job_id = p_job_id AND worker_id = p_worker_id;
    IF FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Р’С‹ СѓР¶Рµ РѕС‚РєР»РёРєР°Р»РёСЃСЊ РЅР° СЌС‚Рѕ Р·Р°РґР°РЅРёРµ', 'code', 'duplicate');
    END IF;

    IF v_job.current_workers >= v_job.max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'РњРµСЃС‚Р° Р·Р°РїРѕР»РЅРµРЅС‹', 'code', 'no_slots');
    END IF;

    INSERT INTO applications (job_id, worker_id, status, created_at, updated_at)
    VALUES (p_job_id, p_worker_id, 'pending', NOW(), NOW());

    RETURN jsonb_build_object(
        'success', true,
        'employer_id', v_job.employer_id,
        'job_id', p_job_id
    );
END;
$$;

GRANT EXECUTE ON FUNCTION accept_application(uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION reject_application(uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION delete_job_cascade(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION delete_user_cascade(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION apply_job_atomic(uuid, uuid) TO service_role;
-- 092_fix_delete_user_cascade.sql
-- Р Р°СЃС€РёСЂРµРЅРЅР°СЏ РІРµСЂСЃРёСЏ delete_user_cascade: РїРѕР»РЅР°СЏ РѕС‡РёСЃС‚РєР° РІСЃРµС… СЃРІСЏР·Р°РЅРЅС‹С… РґР°РЅРЅС‹С….
-- Р”Р»СЏ employer вЂ” РєР°СЃРєР°РґРЅРѕРµ СѓРґР°Р»РµРЅРёРµ Р·Р°РґР°РЅРёР№ С‡РµСЂРµР· delete_job_cascade.
-- Р”Р»СЏ audit_log вЂ” РѕР±РЅСѓР»РµРЅРёРµ user_id (РЅРµ СѓРґР°Р»РµРЅРёРµ Р·Р°РїРёСЃРё).

DROP FUNCTION IF EXISTS delete_user_cascade(uuid);
CREATE OR REPLACE FUNCTION delete_user_cascade(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_role text;
    v_job_id uuid;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ РЅРµ РЅР°Р№РґРµРЅ', 'code', 'not_found');
    END IF;

    -- 1. Р”Р»СЏ employer вЂ” РєР°СЃРєР°РґРЅРѕ СѓРґР°Р»РёС‚СЊ РІСЃРµ Р·Р°РґР°РЅРёСЏ
    IF v_role = 'employer' THEN
        FOR v_job_id IN SELECT id FROM jobs WHERE employer_id = p_user_id LOOP
            PERFORM delete_job_cascade(v_job_id);
        END LOOP;
    END IF;

    -- 2. РЈРґР°Р»РёС‚СЊ Р·Р°СЏРІРєРё СЂР°Р±РѕС‚РЅРёРєР°
    DELETE FROM applications WHERE worker_id = p_user_id;

    -- 3. РЈРґР°Р»РёС‚СЊ СѓРІРµРґРѕРјР»РµРЅРёСЏ
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM notification_outbox WHERE user_id = p_user_id;

    -- 4. РЈРґР°Р»РёС‚СЊ РёР·Р±СЂР°РЅРЅРѕРµ
    DELETE FROM favorites WHERE user_id = p_user_id OR employer_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;

    -- 5. РЈРґР°Р»РёС‚СЊ С‡С‘СЂРЅС‹Рµ СЃРїРёСЃРєРё
    DELETE FROM blacklists WHERE user_id = p_user_id OR blocked_user_id = p_user_id;

    -- 6. РЈРґР°Р»РёС‚СЊ СЂРµР№С‚РёРЅРіРё
    DELETE FROM ratings WHERE rater_id = p_user_id OR rated_user_id = p_user_id;

    -- 7. РЈРґР°Р»РёС‚СЊ РїСЂРёРіР»Р°С€РµРЅРёСЏ
    DELETE FROM invitations WHERE employer_id = p_user_id OR worker_id = p_user_id;

    -- 8. РЈРґР°Р»РёС‚СЊ РЅР°РІС‹РєРё
    DELETE FROM user_skills WHERE user_id = p_user_id;

    -- 9. РЈРґР°Р»РёС‚СЊ push-РїРѕРґРїРёСЃРєРё
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;

    -- 10. РЈРґР°Р»РёС‚СЊ СЃРѕРѕР±С‰РµРЅРёСЏ
    DELETE FROM messages WHERE sender_id = p_user_id OR receiver_id = p_user_id;

    -- 11. РЈРґР°Р»РёС‚СЊ РїР»Р°С‚РµР¶Рё
    DELETE FROM job_payments WHERE payer_id = p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id = p_user_id;

    -- 12. РћР±РЅСѓР»РёС‚СЊ audit_log (СЃРѕС…СЂР°РЅРёС‚СЊ РёСЃС‚РѕСЂРёСЋ РґРµР№СЃС‚РІРёР№)
    UPDATE audit_log SET user_id = NULL WHERE user_id = p_user_id;

    -- 13. РЈРґР°Р»РёС‚СЊ РїСЂРѕС„РёР»СЊ
    DELETE FROM profiles WHERE id = p_user_id;

    RETURN jsonb_build_object('success', true, 'deleted_user_id', p_user_id, 'role', v_role);
END;
$$;

GRANT EXECUTE ON FUNCTION delete_user_cascade(uuid) TO service_role;
-- 093_add_updated_at_triggers.sql
-- РђРІС‚РѕРѕР±РЅРѕРІР»РµРЅРёРµ updated_at РїСЂРё UPDATE РґР»СЏ РєР»СЋС‡РµРІС‹С… С‚Р°Р±Р»РёС†.
-- РћР±РµСЃРїРµС‡РёРІР°РµС‚ РєРѕРЅСЃРёСЃС‚РµРЅС‚РЅРѕСЃС‚СЊ РІСЂРµРјРµРЅРЅС‹С… РјРµС‚РѕРє РЅР° СѓСЂРѕРІРЅРµ Р‘Р”.

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- profiles
DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- jobs
DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- applications
DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications;
CREATE TRIGGER trg_applications_updated_at
    BEFORE UPDATE ON applications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- employer_subscriptions
DROP TRIGGER IF EXISTS trg_employer_subscriptions_updated_at ON employer_subscriptions;
CREATE TRIGGER trg_employer_subscriptions_updated_at
    BEFORE UPDATE ON employer_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
ALTER TABLE notifications DROP COLUMN IF EXISTS shift_id;
ALTER TABLE profiles DROP COLUMN IF EXISTS religion;
-- 096: Р”РѕР±Р°РІР»РµРЅРёРµ РїРѕР»СЏ consented_at РІ profiles (152-Р¤Р— вЂ” СЃРѕРіР»Р°СЃРёРµ СЃ СѓСЃР»РѕРІРёСЏРјРё)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS consented_at TIMESTAMPTZ;
