-- ============================================================================
-- Миграция 086: Исправить delete_job_cascade — гарантировать удаление через FK
-- Проблема: в ранних версиях использовался ILIKE '%uuid%' для поиска уведомлений,
-- что ненадёжно и медленно. Таблица notifications имеет колонку job_id (FK),
-- поэтому используем DELETE WHERE job_id = p_job_id.
-- Также удаляем orphaned-уведомления через ILIKE (оставлено как страховка).
-- ============================================================================
DROP FUNCTION IF EXISTS public.delete_job_cascade(uuid) CASCADE;

CREATE FUNCTION public.delete_job_cascade(p_job_id uuid)
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
