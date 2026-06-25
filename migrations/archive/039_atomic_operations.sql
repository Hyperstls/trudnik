-- 039_atomic_operations.sql
-- Atomic RPC-процедуры для Supabase (этап 4.3)
-- Все с SECURITY DEFINER, возвращают json.
-- 
-- Использование из Python:
--   supabase.rpc('accept_application', {'job_id': ..., 'app_id': ...})
--   supabase.rpc('reject_application', {'job_id': ..., 'app_id': ...})
--   supabase.rpc('delete_job_cascade', {'job_id': ...})
--   supabase.rpc('delete_user_cascade', {'user_id': ...})

BEGIN;

-- ============================================================
-- 1. accept_application(job_id, app_id)
-- Атомарный accept: увеличивает current_workers, меняет статус
-- отклика на 'accepted', возвращает результат
-- ============================================================
CREATE OR REPLACE FUNCTION accept_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_count int;
    v_new_status text;
    v_result json;
BEGIN
    -- 1. Блокирующая проверка: получить текущее состояние задания
    SELECT current_workers, max_workers, status
    INTO v_current_workers, v_max_workers, v_job_status
    FROM jobs
    WHERE id = p_job_id
    FOR UPDATE;  -- row-level lock

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;

    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
    END IF;

    -- 2. Увеличить счётчик
    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE jobs
    SET status = v_new_status,
        current_workers = v_new_count
    WHERE id = p_job_id;

    -- 3. Принять отклик
    UPDATE applications
    SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status = 'pending';

    IF NOT FOUND THEN
        -- Откат: уменьшить счётчик обратно
        UPDATE jobs
        SET status = v_job_status,
            current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    -- 4. Отклонить остальные pending-отклики на это задание
    UPDATE applications
    SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    v_result := json_build_object(
        'success', true,
        'new_status', 'accepted',
        'current_workers', v_new_count,
        'job_status', v_new_status,
        'message', 'Работник принят'
    );

    RETURN v_result;
END;
$$;


-- ============================================================
-- 2. reject_application(job_id, app_id)
-- Атомарный reject: если accepted — уменьшает current_workers,
-- меняет статус отклика на 'rejected', возвращает результат
-- ============================================================
CREATE OR REPLACE FUNCTION reject_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_status text;
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_workers int;
    v_new_job_status text;
    v_result json;
BEGIN
    -- Получить статус отклика
    SELECT status INTO v_current_status
    FROM applications
    WHERE id = p_app_id AND job_id = p_job_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Отклик не найден');
    END IF;

    -- Если отклик был accepted — нужно уменьшить счётчик
    IF v_current_status = 'accepted' THEN
        SELECT current_workers, max_workers, status
        INTO v_current_workers, v_max_workers, v_job_status
        FROM jobs
        WHERE id = p_job_id
        FOR UPDATE;

        v_new_workers := GREATEST(0, v_current_workers - 1);
        v_new_job_status := CASE WHEN v_new_workers = 0 THEN 'open' ELSE 'completed' END;

        UPDATE jobs
        SET current_workers = v_new_workers,
            status = v_new_job_status
        WHERE id = p_job_id;

        -- Отклонить отклик
        UPDATE applications
        SET status = 'rejected'
        WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true,
            'new_status', 'rejected',
            'current_workers', v_new_workers,
            'job_status', v_new_job_status,
            'message', 'Работник отклонён'
        );
    ELSE
        -- Обычное отклонение (pending → rejected)
        UPDATE applications
        SET status = 'rejected'
        WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true,
            'new_status', 'rejected',
            'message', 'Отклик отклонён'
        );
    END IF;

    RETURN v_result;
END;
$$;


-- ============================================================
-- 3. delete_job_cascade(job_id)
-- Каскадное удаление задания и всех связанных записей
-- ============================================================
CREATE OR REPLACE FUNCTION delete_job_cascade(
    p_job_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_deleted_apps int;
    v_deleted_skills int;
    v_deleted_photos int;
    v_deleted_favorites int;
    v_deleted_invitations int;
    v_deleted_notifications int;
BEGIN
    -- Проверяем, существует ли задание
    IF NOT EXISTS (SELECT 1 FROM jobs WHERE id = p_job_id) THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Удаляем связанные записи
    DELETE FROM applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM job_favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    -- Уведомления, содержащие job_id в тексте
    DELETE FROM notifications WHERE message ILIKE '%' || p_job_id::text || '%';
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    -- Само задание
    DELETE FROM jobs WHERE id = p_job_id;

    RETURN json_build_object(
        'success', true,
        'deleted', json_build_object(
            'applications', v_deleted_apps,
            'job_skills', v_deleted_skills,
            'job_photos', v_deleted_photos,
            'job_favorites', v_deleted_favorites,
            'invitations', v_deleted_invitations,
            'notifications', v_deleted_notifications
        ),
        'message', 'Задание удалено'
    );
END;
$$;


-- ============================================================
-- 4. delete_user_cascade(user_id)
-- Каскадное удаление пользователя и всех связанных записей
-- ============================================================
CREATE OR REPLACE FUNCTION delete_user_cascade(
    p_user_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_role text;
    v_deleted json;
BEGIN
    -- Получить роль пользователя
    SELECT role INTO v_role FROM profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Пользователь не найден');
    END IF;

    -- Если работодатель — удалить все его задания каскадно
    IF v_role = 'employer' THEN
        PERFORM delete_job_cascade(job.id)
        FROM (SELECT id FROM jobs WHERE employer_id = p_user_id) AS job;
    END IF;

    -- Удалить связанные записи
    DELETE FROM applications WHERE worker_id = p_user_id;
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE target_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE blocked_user_id = p_user_id;
    DELETE FROM ratings WHERE rater_user_id = p_user_id;
    DELETE FROM ratings WHERE rated_user_id = p_user_id;
    DELETE FROM invitations WHERE employer_id = p_user_id;
    DELETE FROM invitations WHERE worker_id = p_user_id;
    DELETE FROM user_skills WHERE user_id = p_user_id;
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;
    DELETE FROM messages WHERE sender_id = p_user_id;

    -- Удалить профиль
    DELETE FROM profiles WHERE id = p_user_id;

    RETURN json_build_object(
        'success', true,
        'message', 'Пользователь удалён'
    );
END;
$$;

COMMIT;
