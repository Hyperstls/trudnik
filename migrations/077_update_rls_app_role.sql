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