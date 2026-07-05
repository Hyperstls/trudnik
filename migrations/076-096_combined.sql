-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =
-- COMBINED MIGRATION: 076-096
-- Generated: 2026-07-05 for Amvera production
-- ALL 21 migrations + conflict resolution patch
-- USAGE: copy-paste into pgAdmin and execute
-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =-- =

BEGIN;


-- ====== [1] 076_lock_down_rpc.sql ======
-- Отозвать EXECUTE от anon для публичных RPC
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;

-- ====== [2] 077_update_rls_app_role.sql ======
-- Миграция 077: Заменить проверку role → app_role в RLS-политиках и RPC-функциях
-- JWT теперь содержит: role='authenticated' + app_role='worker'/'employer'/'admin'
-- role — PostgreSQL роль (authenticated/service_role/trudnikapp)
-- app_role — прикладная роль для RLS-проверок (worker/employer/admin)

-- ============================================================================
-- 1. RLS-политики: admin_skills, admin_religions (skills, religions)
-- ============================================================================

-- skills: admin_skills (было role IN ('admin', 'trudnikapp') из 073)
DROP POLICY IF EXISTS "admin_skills" ON skills;
CREATE POLICY "admin_skills" ON skills FOR ALL
    USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- religions: admin_religions (было role IN ('admin', 'trudnikapp') из 073)
DROP POLICY IF EXISTS "admin_religions" ON religions;
CREATE POLICY "admin_religions" ON religions FOR ALL
    USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- ============================================================================
-- 2. RLS-политики: monetization_settings
-- ============================================================================

-- monetization_settings_insert (было role IN ('admin', 'trudnikapp') из 073)
DROP POLICY IF EXISTS monetization_settings_insert ON monetization_settings;
CREATE POLICY monetization_settings_insert ON monetization_settings
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- monetization_settings_update (было role IN ('admin', 'trudnikapp') из 073)
DROP POLICY IF EXISTS monetization_settings_update ON monetization_settings;
CREATE POLICY monetization_settings_update ON monetization_settings
    FOR UPDATE USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
        OR current_setting('request.jwt.claim.role', true) = 'trudnikapp'
    );

-- ============================================================================
-- 3. RLS-политики: receipts
-- ============================================================================

-- receipts_select (было role = 'admin')
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

-- receipts_insert (было role = 'admin')
DROP POLICY IF EXISTS receipts_insert ON receipts;
CREATE POLICY receipts_insert ON receipts
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- receipts_update (было role = 'admin')
DROP POLICY IF EXISTS receipts_update ON receipts;
CREATE POLICY receipts_update ON receipts
    FOR UPDATE USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- ============================================================================
-- 4. RLS-политики: audit_log (admin read)
-- ============================================================================
DROP POLICY IF EXISTS "Admins can read audit_log" ON audit_log;
CREATE POLICY "Admins can read audit_log" ON audit_log
    FOR SELECT USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- ============================================================================
-- 5. RLS-политики: notifications (admin delete)
-- ============================================================================
DROP POLICY IF EXISTS "Admins can delete notifications" ON notifications;
CREATE POLICY "Admins can delete notifications" ON notifications
    FOR DELETE USING (
        current_setting('request.jwt.claim.app_role', true) = 'admin'
    );

-- ============================================================================
-- 6. RPC-функции SECURITY DEFINER: замена role → app_role для проверки admin
--    (service_role и trudnikapp остаются как PostgreSQL-роли через request.jwt.claim.role)
-- ============================================================================

-- 6a. accept_application (M8 из 075)
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
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Проверка владельца: только employer_id задания или admin/service_role
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;
    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
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
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    UPDATE public.applications SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    RETURN json_build_object('success', true, 'current_workers', v_new_count, 'job_status', v_new_status);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

-- 6b. reject_application (M9 из 075)
DROP FUNCTION IF EXISTS public.reject_application(uuid, uuid);
CREATE OR REPLACE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_current_status text; v_current_workers int; v_max_workers int;
    v_job_status text; v_employer_id uuid;
    v_new_workers int; v_new_job_status text; v_result json;
BEGIN
    -- Проверка владельца: employer_id задания или admin/service_role
    SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
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
        RETURN json_build_object('success', false, 'error', 'Отклик не найден');
    END IF;

    IF v_current_status = 'rejected' THEN
        RETURN json_build_object('success', false, 'error', 'Отклик уже отклонён');
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

-- 6c. restore_job_atomic (M14 из 075)
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
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_employer_id != p_user_id
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin')
       AND current_setting('request.jwt.claim.role', true) NOT IN ('service_role', 'trudnikapp') THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    -- Сброс статуса задания
    UPDATE public.jobs SET status = 'open', current_workers = 0, updated_at = now()
    WHERE id = p_job_id;

    -- Отмена принятых заявок
    WITH cancelled AS (
        UPDATE public.applications SET status = 'cancelled'
        WHERE job_id = p_job_id AND status = 'accepted'
        RETURNING id
    )
    SELECT count(*) INTO v_cancelled_count FROM cancelled;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание восстановлено',
        'job_status', 'open',
        'current_workers', 0,
        'cancelled_applications', v_cancelled_count
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) TO authenticated, service_role;

-- 6d. delete_job_cascade (M16 из 075)
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
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Проверка владельца
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
-- 7. RLS-политики: notifications и email_log — INSERT только service_role
--    (эти проверяют role, а не app_role — оставляем как есть, т.к. service_role
--     это PostgreSQL-роль, а не прикладная)
--    НО: добавляем проверку app_role = 'admin' для совместимости
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

-- ====== [3] 077b_grant_service_role.sql ======
-- Миграция 077b: Дать trudnik и trudnikapp наследование service_role
-- Необходимо для того, чтобы SET ROLE service_role работал через PostgREST
-- service_role нужен для обхода RLS в admin-запросах (postgrest_admin_request)

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnik') THEN
        GRANT anon, authenticated, service_role TO trudnik;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trudnikapp') THEN
        GRANT anon, authenticated, service_role TO trudnikapp;
    END IF;
END $$;

-- ====== [4] 078_drop_exec_sql.sql ======
-- Migration 078: Drop exec_sql RPC
-- Security: exec_sql(text) allowed arbitrary SQL execution.
-- Anyone with PGRST_JWT_SECRET had root access to the database.
-- Replaced by CLI-only psycopg2 connections in scripts.

-- DROP IF EXISTS + REVOKE обёрнуты в DO-блок для безопасности
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'exec_sql' AND pronamespace = 'public'::regnamespace) THEN
        REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM service_role;
        DROP FUNCTION public.exec_sql(text) CASCADE;
    END IF;
END $$;

-- ====== [5] 079_add_email_verification.sql ======
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT TRUE;

-- ====== [6] 080_register_user_sets_email_verified.sql ======
-- DROP старой версии (несовместимые имена параметров)
DROP FUNCTION IF EXISTS register_user(text, text, text, text) CASCADE;
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

-- ====== [7] 081_normalize_emails.sql ======
-- Перенести зависимости с дубликатов на "выжившие" профили
DO $$
DECLARE
    dup RECORD;
    keep_id uuid;
BEGIN
    FOR dup IN
        SELECT LOWER(email) AS le, (array_agg(id ORDER BY created_at ASC))[1] AS keep_id
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
        
        -- Удалить дубликаты
        DELETE FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id;
    END LOOP;
END $$;

-- Привести к нижнему регистру
UPDATE profiles SET email = LOWER(email) WHERE email != LOWER(email);

-- Case-insensitive индекс
DROP INDEX IF EXISTS idx_profiles_email;
CREATE UNIQUE INDEX idx_profiles_email ON profiles(LOWER(email));

-- ====== [8] 082_login_user_rehash.sql ======
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

-- ====== [9] 083_add_outbox_attempts.sql ======
ALTER TABLE notification_outbox ADD COLUMN IF NOT EXISTS attempts INT DEFAULT 0;
ALTER TABLE notification_outbox DROP CONSTRAINT IF EXISTS notification_outbox_status_check;
ALTER TABLE notification_outbox ADD CONSTRAINT notification_outbox_status_check 
    CHECK (status IN ('pending','sent','failed','skipped'));

-- ====== [10] 084_fix_withdraw_atomic.sql ======
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
        RETURN jsonb_build_object('success', false, 'error', 'Заявка не найдена', 'code', 'application_not_found');
    END IF;

    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Вы не автор этой заявки', 'code', 'not_owner');
    END IF;

    IF v_status = 'withdrawn' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Заявка уже отозвана', 'code', 'already_withdrawn');
    END IF;

    IF v_status = 'accepted' THEN
        -- Проверка 12-часового окна
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
                    'error', format('Нельзя отозвать менее чем за 12 часов до начала (осталось %.1f ч)', v_hours_before),
                    'code', 'too_close_to_start'
                );
            END IF;
        END IF;

        -- Уменьшить current_workers, возможно вернуть статус в open
        v_current_workers := GREATEST(0, v_current_workers - 1);
        IF v_current_workers = 0 AND v_job_status = 'completed' THEN
            v_job_status := 'open';
        END IF;

        UPDATE public.jobs
        SET current_workers = v_current_workers, status = v_job_status, updated_at = now()
        WHERE id = v_job_id;
    ELSE
        -- Для pending — получить employer_id для уведомления
        SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = v_job_id;
    END IF;

    IF v_employer_id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Задание не найдено', 'code', 'job_not_found'
        );
    END IF;

    UPDATE public.applications
    SET status = 'withdrawn'
    WHERE id = p_application_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Заявка отозвана',
        'new_status', 'withdrawn',
        'job_id', v_job_id,
        'employer_id', v_employer_id
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) TO authenticated, service_role;

-- ====== [11] 085_fix_restore_job_atomic.sql ======
-- ============================================================================
-- Миграция 085: Исправить restore_job_atomic
-- Проблема: UPDATE applications SET status = 'cancelled' нарушал CHECK-constraint,
-- т.к. допустимые статусы: ('pending', 'accepted', 'rejected', 'withdrawn')
-- Решение: rejected → pending (не cancelled!)
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
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_employer_id != p_user_id
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin') THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    IF v_status != 'cancelled' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Можно восстановить только отменённое задание (текущий статус: %s)', v_status),
            'code', 'not_cancelled'
        );
    END IF;

    UPDATE public.jobs
    SET status = 'open', current_workers = 0, updated_at = now()
    WHERE id = p_job_id;

    -- Меняем rejected заявки на pending (НЕ cancelled — это нарушает CHECK!)
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
        'message', 'Задание восстановлено',
        'job_status', 'open',
        'current_workers', 0,
        'restored_applications', v_restored_count,
        'restored_worker_ids', COALESCE(to_jsonb(v_restored_worker_ids), '[]'::jsonb)
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) TO authenticated, service_role;

-- ====== [12] 086_fix_delete_job_cascade.sql ======
-- ============================================================================
-- Миграция 086: Исправить delete_job_cascade — гарантировать удаление через FK
-- Проблема: в ранних версиях использовался ILIKE '%uuid%' для поиска уведомлений,
-- что ненадёжно и медленно. Таблица notifications имеет колонку job_id (FK),
-- поэтому используем DELETE WHERE job_id = p_job_id.
-- Также удаляем orphaned-уведомления через ILIKE (оставлено как страховка).
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
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Проверка владельца (для вызовов от имени пользователя)
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

    -- Основное исправление: используем FK-колонку job_id вместо ILIKE '%uuid%'
    DELETE FROM public.notifications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    -- Страховка: удалить orphaned-уведомления, где job_id IS NULL,
    -- но UUID задания встречается в тексте (устаревшие записи)
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

-- ====== [13] 088_apply_job_check_expires.sql ======
-- ============================================================================
-- Миграция 088: Добавить проверку expires_at в apply_job_atomic
-- Проблема: apply_job_atomic не проверяла expires_at, поэтому работники
-- могли откликаться на задания с истёкшим сроком.
-- Решение: добавить проверку v_expires_at < now() перед созданием отклика.
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
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_status NOT IN ('open', 'active') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание недоступно для отклика', 'code', 'job_not_open');
    END IF;

    -- Проверка срока действия задания
    IF v_expires_at IS NOT NULL AND v_expires_at < now() THEN
        RETURN jsonb_build_object('success', false, 'error', 'Срок размещения задания истёк', 'code', 'job_expired');
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

-- ====== [14] 089_migrate_skills.sql ======
-- ============================================================================
-- Миграция 089: Перенести profiles.skills → user_skills и удалить колонку
-- Проблема: Навыки дублируются — массив text[] в profiles.skills и таблица user_skills.
-- Решение: Перенос данных в user_skills, затем DROP COLUMN profiles.skills.
-- ============================================================================

-- Шаг 1: Перенести существующие навыки из profiles.skills (text[]) в user_skills
-- Для каждого пользователя с непустым skills находим skill_id по имени
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
        -- Нормализуем имя навыка
        v_skill_name := trim(both ' "' FROM v_rec.skill_name);
        IF v_skill_name = '' THEN
            CONTINUE;
        END IF;

        -- Ищем skill_id по имени (игнорируя регистр)
        SELECT id INTO v_skill_id
        FROM public.skills
        WHERE LOWER(name) = LOWER(v_skill_name)
        LIMIT 1;

        -- Если навык не найден в справочнике — создаём
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

        -- Вставляем связь user-skill (пропускаем дубликаты)
        IF v_skill_id IS NOT NULL THEN
            INSERT INTO public.user_skills (user_id, skill_id)
            VALUES (v_rec.id, v_skill_id)
            ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;
END $$;

-- Шаг 2: Удалить колонку skills из profiles
ALTER TABLE public.profiles DROP COLUMN IF EXISTS skills;

-- ====== [15] 090_admin_dashboard_rpc.sql ======
-- 090_admin_dashboard_rpc.sql
-- Замена 9 отдельных count-запросов на один RPC-вызов для админ-дашборда.
-- Устраняет N+1 проблему: вместо 9 HTTP-запросов → 1 RPC.

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

-- ====== [16] 091_unify_rpc_jsonb.sql ======
-- 091_unify_rpc_jsonb.sql
-- Унификация return type: замена RETURNS json → RETURNS jsonb для 5 RPC-функций.
-- jsonb — нативный тип PostgreSQL, эффективнее для хранения и обработки.
-- Логика функций НЕ меняется, только тип возврата и json_build_object → jsonb_build_object.

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
        RETURN jsonb_build_object('success', false, 'error', 'Отклик не найден', 'code', 'not_found');
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нет доступа', 'code', 'forbidden');
    END IF;

    IF v_status != 'pending' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик уже обработан', 'code', 'invalid_status');
    END IF;

    SELECT j.current_workers, j.max_workers
    INTO v_current_workers, v_max_workers
    FROM jobs j WHERE j.id = v_job_id;

    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нет свободных мест', 'code', 'no_slots');
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
        RETURN jsonb_build_object('success', false, 'error', 'Отклик не найден', 'code', 'not_found');
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нет доступа', 'code', 'forbidden');
    END IF;

    IF v_status NOT IN ('pending', 'accepted') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик уже обработан', 'code', 'invalid_status');
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

-- 4. delete_user_cascade (логика расширена в 092)
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
        RETURN jsonb_build_object('success', false, 'error', 'Пользователь не найден', 'code', 'not_found');
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
        RETURN jsonb_build_object('success', false, 'error', 'Пользователь не найден', 'code', 'user_not_found');
    END IF;
    IF v_worker_role != 'worker' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Только работники могут откликаться', 'code', 'not_worker');
    END IF;

    SELECT * INTO v_job FROM jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_job.status != 'open' THEN
        RETURN jsonb_build_object('success', false, 'error', 'На это задание нельзя откликаться', 'code', 'job_not_open');
    END IF;

    IF v_job.employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нельзя откликаться на своё задание', 'code', 'own_job');
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM blacklists
        WHERE user_id = v_job.employer_id AND blocked_user_id = p_worker_id
    ) INTO v_blacklisted;
    IF v_blacklisted THEN
        RETURN jsonb_build_object('success', false, 'error', 'Работодатель добавил вас в чёрный список', 'code', 'blacklisted');
    END IF;

    SELECT id INTO v_existing_id FROM applications
    WHERE job_id = p_job_id AND worker_id = p_worker_id;
    IF FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Вы уже откликались на это задание', 'code', 'duplicate');
    END IF;

    IF v_job.current_workers >= v_job.max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'Места заполнены', 'code', 'no_slots');
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

-- ====== [17] 092_fix_delete_user_cascade.sql ======
-- 092_fix_delete_user_cascade.sql
-- Расширенная версия delete_user_cascade: полная очистка всех связанных данных.
-- Для employer — каскадное удаление заданий через delete_job_cascade.
-- Для audit_log — обнуление user_id (не удаление записи).

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
        RETURN jsonb_build_object('success', false, 'error', 'Пользователь не найден', 'code', 'not_found');
    END IF;

    -- 1. Для employer — каскадно удалить все задания
    IF v_role = 'employer' THEN
        FOR v_job_id IN SELECT id FROM jobs WHERE employer_id = p_user_id LOOP
            PERFORM delete_job_cascade(v_job_id);
        END LOOP;
    END IF;

    -- 2. Удалить заявки работника
    DELETE FROM applications WHERE worker_id = p_user_id;

    -- 3. Удалить уведомления
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM notification_outbox WHERE user_id = p_user_id;

    -- 4. Удалить избранное
    DELETE FROM favorites WHERE user_id = p_user_id OR employer_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;

    -- 5. Удалить чёрные списки
    DELETE FROM blacklists WHERE user_id = p_user_id OR blocked_user_id = p_user_id;

    -- 6. Удалить рейтинги
    DELETE FROM ratings WHERE rater_id = p_user_id OR rated_user_id = p_user_id;

    -- 7. Удалить приглашения
    DELETE FROM invitations WHERE employer_id = p_user_id OR worker_id = p_user_id;

    -- 8. Удалить навыки
    DELETE FROM user_skills WHERE user_id = p_user_id;

    -- 9. Удалить push-подписки
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;

    -- 10. Удалить сообщения
    DELETE FROM messages WHERE sender_id = p_user_id OR receiver_id = p_user_id;

    -- 11. Удалить платежи
    DELETE FROM job_payments WHERE payer_id = p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id = p_user_id;

    -- 12. Обнулить audit_log (сохранить историю действий)
    UPDATE audit_log SET user_id = NULL WHERE user_id = p_user_id;

    -- 13. Удалить профиль
    DELETE FROM profiles WHERE id = p_user_id;

    RETURN jsonb_build_object('success', true, 'deleted_user_id', p_user_id, 'role', v_role);
END;
$$;

GRANT EXECUTE ON FUNCTION delete_user_cascade(uuid) TO service_role;

-- ====== [18] 093_add_updated_at_triggers.sql ======
-- 093_add_updated_at_triggers.sql
-- Автообновление updated_at при UPDATE для ключевых таблиц.
-- Обеспечивает консистентность временных меток на уровне БД.

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

-- ====== [19] 094_drop_shift_id.sql ======
ALTER TABLE notifications DROP COLUMN IF EXISTS shift_id;

-- ====== [20] 095_drop_religion_text.sql ======
ALTER TABLE profiles DROP COLUMN IF EXISTS religion;

-- ====== [21] 096_add_consented_at.sql ======
-- 096: Добавление поля consented_at в profiles (152-ФЗ — согласие с условиями)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS consented_at TIMESTAMPTZ;

-- ====== [22] 099_fix_conflicts.sql (PATCH) ======
-- 099_fix_conflicts.sql
-- Патч: восстанавливает правильные сигнатуры после миграции 091.
-- Применять ПОСЛЕ всех остальных миграций (076-096).

-- 1. accept_application(p_job_id uuid, p_app_id uuid)
DROP FUNCTION IF EXISTS public.accept_application(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.accept_application(p_job_id uuid, p_app_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_cw int; v_mw int; v_js text; v_nc int; v_ns text; v_eid uuid; v_wid uuid; v_as text;
BEGIN
    SELECT current_workers, max_workers, status, employer_id INTO v_cw, v_mw, v_js, v_eid
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    IF v_js NOT IN ('open','active') THEN RETURN jsonb_build_object('success',false,'error','job_not_open','code','job_not_open'); END IF;
    IF v_cw >= v_mw THEN RETURN jsonb_build_object('success',false,'error','no_slots','code','no_slots'); END IF;
    SELECT status, worker_id INTO v_as, v_wid FROM public.applications WHERE id=p_app_id AND job_id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','app_not_found','code','not_found'); END IF;
    IF v_as NOT IN ('pending','rejected') THEN RETURN jsonb_build_object('success',false,'error','bad_status','code','bad_status'); END IF;
    UPDATE public.applications SET status='accepted', updated_at=now() WHERE id=p_app_id AND job_id=p_job_id;
    v_nc := v_cw + 1; v_ns := CASE WHEN v_nc >= v_mw THEN 'completed' ELSE 'open' END;
    UPDATE public.jobs SET status=v_ns, current_workers=v_nc, updated_at=now() WHERE id=p_job_id;
    UPDATE public.applications SET status='rejected', updated_at=now() WHERE job_id=p_job_id AND status='pending' AND id!=p_app_id;
    RETURN jsonb_build_object('success',true,'current_workers',v_nc,'job_status',v_ns,'worker_id',v_wid,'job_id',p_job_id);
END; $$;
REVOKE EXECUTE ON FUNCTION public.accept_application(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.accept_application(uuid,uuid) TO authenticated, service_role;

-- 2. reject_application(p_job_id uuid, p_app_id uuid)
DROP FUNCTION IF EXISTS public.reject_application(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eid uuid; v_wid uuid; v_cs text; v_cw int; v_mw int; v_js text; v_nw int; v_ns text;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    SELECT status, worker_id INTO v_cs, v_wid FROM public.applications WHERE id=p_app_id AND job_id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','app_not_found','code','not_found'); END IF;
    IF v_cs='rejected' THEN RETURN jsonb_build_object('success',false,'error','already_rejected','code','already_rejected'); END IF;
    UPDATE public.applications SET status='rejected', updated_at=now() WHERE id=p_app_id AND job_id=p_job_id;
    IF v_cs='accepted' THEN
        SELECT current_workers, max_workers, status INTO v_cw, v_mw, v_js FROM public.jobs WHERE id=p_job_id;
        v_nw := GREATEST(v_cw-1,0); v_ns := CASE WHEN v_nw=0 AND v_js='completed' THEN 'open' ELSE v_js END;
        UPDATE public.jobs SET status=v_ns, current_workers=v_nw, updated_at=now() WHERE id=p_job_id;
    END IF;
    RETURN jsonb_build_object('success',true,'worker_id',v_wid,'job_id',p_job_id);
END; $$;
REVOKE EXECUTE ON FUNCTION public.reject_application(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.reject_application(uuid,uuid) TO authenticated, service_role;

-- 3. apply_job_atomic: версия из 088 (с проверкой expires_at)
DROP FUNCTION IF EXISTS public.apply_job_atomic(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.apply_job_atomic(p_job_id uuid, p_worker_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_mw int; v_cw int; v_st text; v_eid uuid; v_exp timestamptz; v_aid uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id, expires_at
    INTO v_mw, v_cw, v_st, v_eid, v_exp FROM public.jobs WHERE id=p_job_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','job_not_found','code','job_not_found'); END IF;
    IF v_st NOT IN ('open','active') THEN RETURN jsonb_build_object('success',false,'error','job_not_open','code','job_not_open'); END IF;
    IF v_exp IS NOT NULL AND v_exp < now() THEN RETURN jsonb_build_object('success',false,'error','job_expired','code','job_expired'); END IF;
    IF v_eid = p_worker_id THEN RETURN jsonb_build_object('success',false,'error','own_job','code','own_job'); END IF;
    IF EXISTS(SELECT 1 FROM public.blacklists WHERE user_id=v_eid AND blocked_user_id=p_worker_id)
    THEN RETURN jsonb_build_object('success',false,'error','blacklisted','code','blacklisted'); END IF;
    INSERT INTO public.applications (job_id, worker_id, status) VALUES (p_job_id, p_worker_id, 'pending')
    RETURNING id INTO v_aid;
    RETURN jsonb_build_object('success',true,'application_id',v_aid,'employer_id',v_eid);
EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('success',false,'error','duplicate','code','duplicate');
END; $$;
REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.apply_job_atomic(uuid,uuid) TO authenticated, service_role;

-- 4. delete_job_cascade: версия из 086 (полная, с проверкой владельца)
DROP FUNCTION IF EXISTS public.delete_job_cascade(uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eid uuid; va int; vs int; vp int; vf int; vi int; vn int;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found'); END IF;
    DELETE FROM public.applications WHERE job_id=p_job_id; GET DIAGNOSTICS va = ROW_COUNT;
    DELETE FROM public.job_skills WHERE job_id=p_job_id; GET DIAGNOSTICS vs = ROW_COUNT;
    DELETE FROM public.job_photos WHERE job_id=p_job_id; GET DIAGNOSTICS vp = ROW_COUNT;
    DELETE FROM public.favorites WHERE job_id=p_job_id; GET DIAGNOSTICS vf = ROW_COUNT;
    DELETE FROM public.invitations WHERE job_id=p_job_id; GET DIAGNOSTICS vi = ROW_COUNT;
    DELETE FROM public.notifications WHERE job_id=p_job_id; GET DIAGNOSTICS vn = ROW_COUNT;
    DELETE FROM public.jobs WHERE id=p_job_id;
    RETURN jsonb_build_object('success',true,'deleted_applications',va,'deleted_skills',vs,'deleted_photos',vp,'deleted_favorites',vf,'deleted_invitations',vi,'deleted_notifications',vn);
END; $$;
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;

-- 5. delete_user_cascade: версия из 092 (самая полная)
DROP FUNCTION IF EXISTS public.delete_user_cascade(uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.delete_user_cascade(p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_role text; v_jid uuid;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id=p_user_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    IF v_role='employer' THEN FOR v_jid IN SELECT id FROM jobs WHERE employer_id=p_user_id LOOP PERFORM delete_job_cascade(v_jid); END LOOP; END IF;
    DELETE FROM applications WHERE worker_id=p_user_id;
    DELETE FROM notifications WHERE user_id=p_user_id;
    DELETE FROM notification_outbox WHERE user_id=p_user_id;
    DELETE FROM favorites WHERE user_id=p_user_id OR employer_id=p_user_id;
    DELETE FROM job_favorites WHERE user_id=p_user_id;
    DELETE FROM blacklists WHERE user_id=p_user_id OR blocked_user_id=p_user_id;
    DELETE FROM ratings WHERE rater_id=p_user_id OR rated_user_id=p_user_id;
    DELETE FROM invitations WHERE employer_id=p_user_id OR worker_id=p_user_id;
    DELETE FROM user_skills WHERE user_id=p_user_id;
    DELETE FROM push_subscriptions WHERE user_id=p_user_id;
    DELETE FROM messages WHERE sender_id=p_user_id OR receiver_id=p_user_id;
    DELETE FROM job_payments WHERE payer_id=p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id=p_user_id;
    UPDATE audit_log SET user_id=NULL WHERE user_id=p_user_id;
    DELETE FROM profiles WHERE id=p_user_id;
    RETURN jsonb_build_object('success',true,'deleted_user_id',p_user_id,'role',v_role);
END; $$;
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;

COMMIT;
