-- ============================================================================
-- Миграция 069: Исправление критических проблем RPC (search_path, race conditions, гранты)
-- Дата: 2026-06-23
-- 
-- ЧТО ДЕЛАЕТ ЭТОТ СКРИПТ:
--   1. Fix search_path во всех старых RPC (039, 048, 064):
--      замена SET search_path = public на SET search_path = ''
--      + добавление префикса public. ко всем ссылкам на таблицы
--   2. Fix apply_job_atomic: FOR UPDATE на проверку дубликата + явный инкремент current_workers
--   3. Fix cancel_worker_atomic: проверка 12-часового окна до начала задания
--   4. Fix rate_user_atomic: проверка участия обоих пользователей в задании
--   5. Fix accept_application: FOR UPDATE на все applications для задания
--   6. Fix force_complete_job: разрешить active/in_progress (не только open)
--   7. Fix accept_invitation_atomic: проверка существующего статуса заявки
--   8. GRANT права для всех изменённых функций
--
-- ИДЕМПОТЕНТНОСТЬ: Все определения используют CREATE OR REPLACE.
-- ЗАВИСИМОСТИ: Миграции 039, 048, 059, 061, 062, 064 должны быть применены ранее.
-- ============================================================================

BEGIN;

-- ============================================================================
-- Часть 1: Fix search_path + public. префикс для старых RPC (из 039)
-- ============================================================================

-- 1a. accept_application — исправленный search_path + FOR UPDATE на все applications
CREATE OR REPLACE FUNCTION public.accept_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_count int;
    v_new_status text;
    v_result json;
BEGIN
    -- 1. Блокировка ВСЕХ applications для данного задания (предотвращает race condition)
    PERFORM 1 FROM public.applications 
    WHERE job_id = p_job_id 
    FOR UPDATE;

    -- 2. Блокирующая проверка: получить текущее состояние задания
    SELECT current_workers, max_workers, status
    INTO v_current_workers, v_max_workers, v_job_status
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;

    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
    END IF;

    -- 3. Увеличить счётчик
    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE public.jobs
    SET status = v_new_status,
        current_workers = v_new_count
    WHERE id = p_job_id;

    -- 4. Принять отклик (из pending или rejected)
    UPDATE public.applications
    SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status IN ('pending', 'rejected');

    IF NOT FOUND THEN
        -- Откат: уменьшить счётчик обратно
        UPDATE public.jobs
        SET status = v_job_status,
            current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    -- 5. Отклонить остальные pending-отклики на это задание
    UPDATE public.applications
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


-- 1b. reject_application — исправленный search_path + public. префикс
CREATE OR REPLACE FUNCTION public.reject_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
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
    FROM public.applications
    WHERE id = p_app_id AND job_id = p_job_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Отклик не найден');
    END IF;

    -- Если отклик был accepted — нужно уменьшить счётчик
    IF v_current_status = 'accepted' THEN
        SELECT current_workers, max_workers, status
        INTO v_current_workers, v_max_workers, v_job_status
        FROM public.jobs
        WHERE id = p_job_id
        FOR UPDATE;

        v_new_workers := GREATEST(0, v_current_workers - 1);
        v_new_job_status := CASE WHEN v_new_workers = 0 THEN 'open' ELSE 'completed' END;

        UPDATE public.jobs
        SET current_workers = v_new_workers,
            status = v_new_job_status
        WHERE id = p_job_id;

        -- Отклонить отклик
        UPDATE public.applications
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
        UPDATE public.applications
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


-- 1c. delete_job_cascade — исправленный search_path + public. префикс
CREATE OR REPLACE FUNCTION public.delete_job_cascade(
    p_job_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
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
    IF NOT EXISTS (SELECT 1 FROM public.jobs WHERE id = p_job_id) THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Удаляем связанные записи
    DELETE FROM public.applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM public.job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM public.job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM public.job_favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM public.invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    -- Уведомления, содержащие job_id в тексте
    DELETE FROM public.notifications WHERE message ILIKE '%' || p_job_id::text || '%';
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    -- Само задание
    DELETE FROM public.jobs WHERE id = p_job_id;

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


-- 1d. delete_user_cascade — исправленный search_path + public. префикс
CREATE OR REPLACE FUNCTION public.delete_user_cascade(
    p_user_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_role text;
    v_deleted json;
BEGIN
    -- Получить роль пользователя
    SELECT role INTO v_role FROM public.profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Пользователь не найден');
    END IF;

    -- Если работодатель — удалить все его задания каскадно
    IF v_role = 'employer' THEN
        PERFORM public.delete_job_cascade(job.id)
        FROM (SELECT id FROM public.jobs WHERE employer_id = p_user_id) AS job;
    END IF;

    -- Удалить связанные записи
    DELETE FROM public.applications WHERE worker_id = p_user_id;
    DELETE FROM public.notifications WHERE user_id = p_user_id;
    DELETE FROM public.favorites WHERE user_id = p_user_id;
    DELETE FROM public.favorites WHERE target_id = p_user_id;
    DELETE FROM public.job_favorites WHERE user_id = p_user_id;
    DELETE FROM public.blacklists WHERE user_id = p_user_id;
    DELETE FROM public.blacklists WHERE blocked_user_id = p_user_id;
    DELETE FROM public.ratings WHERE rater_user_id = p_user_id;
    DELETE FROM public.ratings WHERE rated_user_id = p_user_id;
    DELETE FROM public.invitations WHERE employer_id = p_user_id;
    DELETE FROM public.invitations WHERE worker_id = p_user_id;
    DELETE FROM public.user_skills WHERE user_id = p_user_id;
    DELETE FROM public.push_subscriptions WHERE user_id = p_user_id;
    DELETE FROM public.messages WHERE sender_id = p_user_id;

    -- Удалить профиль
    DELETE FROM public.profiles WHERE id = p_user_id;

    RETURN json_build_object(
        'success', true,
        'message', 'Пользователь удалён'
    );
END;
$$;


-- ============================================================================
-- Часть 2: Исправление apply_job_atomic (из 048)
-- ============================================================================

-- 2. apply_job_atomic: FOR UPDATE на проверку дубликата + явный инкремент current_workers
CREATE OR REPLACE FUNCTION public.apply_job_atomic(
    p_job_id uuid,
    p_worker_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_max_workers int;
    v_current_workers int;
    v_status text;
    v_employer_id uuid;
    v_blacklisted boolean;
    v_duplicate boolean;
    v_app_id uuid;
BEGIN
    -- 1. Блокировка задания
    SELECT max_workers, current_workers, status, employer_id
    INTO v_max_workers, v_current_workers, v_status, v_employer_id
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    -- 2. Проверить, что задание открыто для откликов
    IF v_status NOT IN ('open', 'active') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание недоступно для отклика', 'code', 'job_not_open');
    END IF;

    -- 3. Проверить, что работник не откликается на собственное задание
    IF v_employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Вы не можете откликаться на собственное задание', 'code', 'own_job');
    END IF;

    -- 4. Проверить, не заблокирован ли работник у этого работодателя
    SELECT EXISTS(
        SELECT 1 FROM public.blacklists
        WHERE user_id = v_employer_id AND blocked_user_id = p_worker_id
    ) INTO v_blacklisted;

    IF v_blacklisted THEN
        RETURN jsonb_build_object('success', false, 'error', 'Вы не можете откликнуться: работодатель добавил вас в чёрный список', 'code', 'blacklisted');
    END IF;

    -- 5. Проверка дубликата с FOR UPDATE
    SELECT EXISTS(
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id AND worker_id = p_worker_id
        FOR UPDATE
    ) INTO v_duplicate;

    IF v_duplicate THEN
        RETURN jsonb_build_object('success', false, 'error', 'Вы уже откликались на это задание', 'code', 'duplicate');
    END IF;

    -- 6. Проверить лимит мест
    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'Достигнут лимит работников', 'code', 'no_slots');
    END IF;

    -- 7. Вставка отклика
    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (p_job_id, p_worker_id, 'pending')
    RETURNING id INTO v_app_id;

    -- 8. Явный инкремент current_workers
    UPDATE public.jobs
    SET current_workers = current_workers + 1,
        status = CASE WHEN current_workers + 1 >= max_workers THEN 'active' ELSE status END
    WHERE id = p_job_id;

    RETURN jsonb_build_object('success', true, 'application_id', v_app_id, 'employer_id', v_employer_id);

EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('success', false, 'error', 'Вы уже откликались на это задание', 'code', 'duplicate');
WHEN OTHERS THEN
    RETURN jsonb_build_object('success', false, 'error', SQLERRM);
END;
$$;


-- ============================================================================
-- Часть 3: Исправление cancel_worker_atomic (из 059/062) — проверка 12-часового окна
-- ============================================================================

CREATE OR REPLACE FUNCTION public.cancel_worker_atomic(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_worker_id uuid;
    v_job_id uuid;
    v_app_status text;
    v_employer_id uuid;
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_workers int;
    v_new_job_status text;
    v_notification_id uuid;
BEGIN
    -- 1. Получить заявку с блокировкой строки
    SELECT worker_id, job_id, status
    INTO v_worker_id, v_job_id, v_app_status
    FROM public.applications
    WHERE id = p_application_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Заявка не найдена',
            'code', 'application_not_found'
        );
    END IF;

    -- 2. Проверить, что заявка в статусе accepted
    IF v_app_status != 'accepted' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя отменить исполнителя в статусе ''%s''', v_app_status),
            'code', 'invalid_status'
        );
    END IF;

    -- 3. Получить задание и проверить владельца
    SELECT employer_id, current_workers, max_workers, status
    INTO v_employer_id, v_current_workers, v_max_workers, v_job_status
    FROM public.jobs
    WHERE id = v_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 4. Проверить, что пользователь — владелец задания
    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    -- 5. Проверка 12-часового окна до начала задания
    IF EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = v_job_id
        AND date_time IS NOT NULL
        AND date_time - INTERVAL '12 hours' <= NOW()
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Отказ от задания невозможен менее чем за 12 часов до начала',
            'code', 'deadline_passed'
        );
    END IF;

    -- 6. Обновить статус заявки на cancelled
    UPDATE public.applications
    SET status = 'cancelled'
    WHERE id = p_application_id;

    -- 7. Уменьшить счётчик занятых мест
    v_new_workers := GREATEST(0, v_current_workers - 1);

    -- Если мест стало 0 и задание было completed/active — возвращаем в open
    IF v_new_workers = 0 AND v_job_status IN ('completed', 'active', 'in_progress') THEN
        v_new_job_status := 'open';
    ELSE
        v_new_job_status := v_job_status;
    END IF;

    UPDATE public.jobs
    SET current_workers = v_new_workers,
        status = v_new_job_status
    WHERE id = v_job_id;

    -- 8. Создать уведомление работнику
    INSERT INTO public.notifications (user_id, type, title, message, data, is_read)
    VALUES (
        v_worker_id,
        'worker_cancelled',
        'Заявка отменена',
        format('Работодатель отменил ваше участие в задании #%s', v_job_id),
        jsonb_build_object('job_id', v_job_id, 'application_id', p_application_id),
        false
    )
    RETURNING id INTO v_notification_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Исполнитель отменён',
        'new_status', 'cancelled',
        'current_workers', v_new_workers,
        'job_status', v_new_job_status,
        'notification_id', v_notification_id
    );
END;
$$;


-- ============================================================================
-- Часть 4: Исправление rate_user_atomic (из 059/062) — проверка участия в задании
-- ============================================================================

CREATE OR REPLACE FUNCTION public.rate_user_atomic(
    p_job_id uuid,
    p_rater_user_id uuid,
    p_rated_user_id uuid,
    p_rating int,
    p_comment text DEFAULT '',
    p_rating_type text DEFAULT 'worker',
    p_target_type text DEFAULT 'worker'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_new_avg numeric(3,1);
    v_new_count int;
BEGIN
    -- 1. Валидация рейтинга
    IF p_rating < 1 OR p_rating > 5 THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Рейтинг должен быть от 1 до 5',
            'code', 'invalid_rating'
        );
    END IF;

    -- 2. Нельзя оценить самого себя
    IF p_rater_user_id = p_rated_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Нельзя оценить самого себя',
            'code', 'self_rating'
        );
    END IF;

    -- 3. Проверить, что задание существует и завершено
    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = p_job_id AND status = 'completed'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оценить можно только завершённое задание',
            'code', 'job_not_completed'
        );
    END IF;

    -- 4. Проверка участия оценивающего в задании
    IF NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id
        AND worker_id = p_rater_user_id
        AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не участвовали в этом задании',
            'code', 'not_participant'
        );
    END IF;

    -- 5. Проверка участия оцениваемого в задании
    IF NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id
        AND worker_id = p_rated_user_id
        AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не участвовал в этом задании',
            'code', 'rated_not_participant'
        );
    END IF;

    -- 6. Проверить, что оцениваемый пользователь существует
    IF NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE id = p_rated_user_id
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    -- 7. UPSERT оценки (один пользователь — одна оценка на задание)
    INSERT INTO public.ratings (
        job_id,
        rater_user_id,
        rated_user_id,
        rating,
        comment,
        rating_type,
        target_type,
        created_at,
        updated_at
    ) VALUES (
        p_job_id,
        p_rater_user_id,
        p_rated_user_id,
        p_rating,
        p_comment,
        p_rating_type,
        p_target_type,
        now(),
        now()
    )
    ON CONFLICT (rater_user_id, job_id)
    DO UPDATE SET
        rating = EXCLUDED.rating,
        comment = EXCLUDED.comment,
        updated_at = now();

    -- 8. Пересчитать средний рейтинг и количество оценок для rated_user_id
    SELECT
        COALESCE(ROUND(AVG(rating)::numeric, 1), 0),
        COUNT(*)::int
    INTO v_new_avg, v_new_count
    FROM public.ratings
    WHERE rated_user_id = p_rated_user_id;

    -- 9. Обновить профиль пользователя
    UPDATE public.profiles
    SET rating = v_new_avg,
        ratings_count = v_new_count
    WHERE id = p_rated_user_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Оценка сохранена',
        'new_avg_rating', v_new_avg,
        'new_ratings_count', v_new_count
    );
END;
$$;


-- ============================================================================
-- Часть 5: Исправление force_complete_job (из 061/062) — разрешить active/in_progress
-- ============================================================================

CREATE OR REPLACE FUNCTION public.force_complete_job(
    p_job_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_accepted_workers uuid[];
BEGIN
    -- 1. Получить задание с блокировкой строки
    SELECT employer_id, status
    INTO v_employer_id, v_status
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 2. Проверить, что пользователь — владелец задания
    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    -- 3. Проверить, что задание в допустимом статусе (open, active, in_progress)
    IF v_status NOT IN ('open', 'active', 'in_progress') THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Задание не может быть завершено в текущем статусе ''%s''', v_status),
            'code', 'invalid_status',
            'current_status', v_status
        );
    END IF;

    -- 4. Массово отклонить все pending-отклики
    UPDATE public.applications
    SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending';

    -- 5. Перевести задание в completed
    UPDATE public.jobs
    SET status = 'completed',
        updated_at = now()
    WHERE id = p_job_id;

    -- 6. Собрать accepted-работников для уведомлений
    SELECT array_agg(DISTINCT worker_id)
    INTO v_accepted_workers
    FROM public.applications
    WHERE job_id = p_job_id AND status = 'accepted';

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание завершено',
        'new_status', 'completed',
        'accepted_worker_ids', COALESCE(to_jsonb(v_accepted_workers), '[]'::jsonb)
    );
END;
$$;


-- ============================================================================
-- Часть 6: Исправление accept_invitation_atomic (из 061/062) — проверка статуса заявки
-- ============================================================================

CREATE OR REPLACE FUNCTION public.accept_invitation_atomic(
    p_invitation_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_job_id uuid;
    v_employer_id uuid;
    v_worker_id uuid;
    v_inv_status text;
    v_job_status text;
    v_current_workers int;
    v_max_workers int;
    v_new_count int;
    v_new_job_status text;
    v_application_id uuid;
    v_existing_app_status text;
BEGIN
    -- 1. Получить приглашение с блокировкой
    SELECT job_id, employer_id, worker_id, status
    INTO v_job_id, v_employer_id, v_worker_id, v_inv_status
    FROM public.invitations
    WHERE id = p_invitation_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Приглашение не найдено',
            'code', 'invitation_not_found'
        );
    END IF;

    -- 2. Проверить, что пользователь — целевой работник
    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Это приглашение адресовано другому пользователю',
            'code', 'not_target'
        );
    END IF;

    -- 3. Проверить, что приглашение в статусе pending
    IF v_inv_status != 'pending' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Приглашение уже %s', v_inv_status),
            'code', 'invitation_not_pending'
        );
    END IF;

    -- 4. Получить задание с блокировкой строки
    SELECT status, current_workers, max_workers
    INTO v_job_status, v_current_workers, v_max_workers
    FROM public.jobs
    WHERE id = v_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 5. Проверить, что задание открыто для откликов
    IF v_job_status != 'open' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Задание в статусе ''%s'' — нельзя принять приглашение', v_job_status),
            'code', 'job_not_open'
        );
    END IF;

    -- 6. Проверить наличие свободных мест
    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Все места заняты (%s из %s)', v_current_workers, v_max_workers),
            'code', 'no_slots'
        );
    END IF;

    -- 7. Проверить существующую заявку — нельзя перезаписать accepted/cancelled
    SELECT status INTO v_existing_app_status
    FROM public.applications
    WHERE job_id = v_job_id AND worker_id = v_worker_id;

    IF v_existing_app_status IS NOT NULL AND v_existing_app_status NOT IN ('pending', 'rejected') THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Невозможно принять приглашение: заявка в статусе ''%s''', v_existing_app_status),
            'code', 'application_not_modifiable'
        );
    END IF;

    -- 8. Создать заявку со статусом accepted (работодатель уже выбрал трудника)
    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (v_job_id, v_worker_id, 'accepted')
    ON CONFLICT (job_id, worker_id) DO UPDATE
        SET status = 'accepted'
    RETURNING id INTO v_application_id;

    -- 9. Инкрементировать current_workers
    v_new_count := v_current_workers + 1;
    IF v_new_count >= v_max_workers THEN
        v_new_job_status := 'completed';
    ELSE
        v_new_job_status := v_job_status;
    END IF;

    UPDATE public.jobs
    SET current_workers = v_new_count,
        status = v_new_job_status,
        updated_at = now()
    WHERE id = v_job_id;

    -- 10. Обновить статус приглашения
    UPDATE public.invitations
    SET status = 'accepted',
        responded_at = now()
    WHERE id = p_invitation_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Приглашение принято',
        'job_id', v_job_id,
        'employer_id', v_employer_id,
        'worker_id', v_worker_id,
        'application_id', v_application_id,
        'current_workers', v_new_count,
        'job_status', v_new_job_status
    );
END;
$$;


-- ============================================================================
-- Часть 7: Права доступа для всех изменённых функций
-- ============================================================================

-- accept_application (039/064)
REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

-- reject_application (039)
REVOKE EXECUTE ON FUNCTION public.reject_application(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;

-- delete_job_cascade (039)
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;

-- delete_user_cascade (039)
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO authenticated, service_role;

-- apply_job_atomic (048)
REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated;

-- cancel_worker_atomic (059/062) — права уже выданы в 062, здесь REVOKE+PUBLIC для безопасности
REVOKE EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) TO authenticated, service_role;

-- rate_user_atomic (059/062) — права уже выданы в 062, здесь REVOKE+PUBLIC для безопасности
REVOKE EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) TO authenticated;

-- force_complete_job (061/062)
REVOKE EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) TO authenticated, service_role;

-- accept_invitation_atomic (061/062)
REVOKE EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) TO authenticated, service_role;

COMMIT;

-- ============================================================================
-- ГОТОВО!
-- 
-- Итого исправлено:
--   1. search_path + public. префикс: accept_application, reject_application,
--      delete_job_cascade, delete_user_cascade, apply_job_atomic
--   2. apply_job_atomic: FOR UPDATE на дубликат + явный инкремент current_workers
--   3. cancel_worker_atomic: проверка 12-часового окна
--   4. rate_user_atomic: проверка участия обоих пользователей в задании
--   5. accept_application: FOR UPDATE на все applications для задания
--   6. force_complete_job: разрешены статусы active/in_progress
--   7. accept_invitation_atomic: проверка существующего статуса заявки
--   8. GRANT права для всех 9 изменённых функций
-- ============================================================================
