-- ============================================================================
-- Миграция 059: Атомарные RPC-процедуры для рефакторинга (Фаза 2)
-- Дата: 2026-06-22
-- Контекст: Группа 2A — 5 RPC для атомарных операций, заменяющих
--   неатомарные цепочки HTTP-запросов из Python-кода.
-- Зависит от: 058_add_native_auth.sql
-- Идемпотентна: CREATE OR REPLACE.
--
-- RPC 1: withdraw_application_atomic  — атомарный отзыв заявки
-- RPC 2: cancel_worker_atomic         — атомарная отмена исполнителя
-- RPC 3: rate_user_atomic             — атомарная оценка + пересчёт рейтинга
-- RPC 4: update_job_status_atomic     — атомарное обновление статуса (state machine)
-- RPC 5: resolve_user_atomic          — быстрый lookup пользователя (замена N+1)
-- ============================================================================

BEGIN;

-- ============================================================================
-- RPC 1: withdraw_application_atomic
-- Атомарно отзывает заявку:
--   - Проверяет, что пользователь — владелец заявки
--   - Проверяет, что заявка в статусе 'pending'
--   - Обновляет статус на 'withdrawn'
--   - Возвращает структурированный JSON
-- ============================================================================
CREATE OR REPLACE FUNCTION public.withdraw_application_atomic(
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
    v_status text;
BEGIN
    -- 1. Получить заявку с блокировкой строки
    SELECT worker_id, job_id, status
    INTO v_worker_id, v_job_id, v_status
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

    -- 2. Проверить, что пользователь — владелец заявки
    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не автор этой заявки',
            'code', 'not_owner'
        );
    END IF;

    -- 3. Проверить, что заявка в статусе pending
    IF v_status != 'pending' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя отозвать заявку в статусе ''%s''', v_status),
            'code', 'invalid_status'
        );
    END IF;

    -- 4. Обновить статус на withdrawn
    UPDATE public.applications
    SET status = 'withdrawn'
    WHERE id = p_application_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Заявка отозвана',
        'new_status', 'withdrawn',
        'job_id', v_job_id
    );
END;
$$;


-- ============================================================================
-- RPC 2: cancel_worker_atomic
-- Атомарно отменяет исполнителя:
--   - Проверяет, что пользователь — владелец задания
--   - Проверяет, что заявка в статусе 'accepted'
--   - Обновляет статус на 'cancelled'
--   - Уменьшает счётчик current_workers
--   - При необходимости переводит задание в 'open'
--   - Создаёт уведомление работнику
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

    -- 5. Обновить статус заявки на cancelled
    UPDATE public.applications
    SET status = 'cancelled'
    WHERE id = p_application_id;

    -- 6. Уменьшить счётчик занятых мест
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

    -- 7. Создать уведомление работнику
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
-- RPC 3: rate_user_atomic
-- Атомарно сохраняет оценку и пересчитывает средний рейтинг пользователя:
--   - Вставляет запись в ratings (UPSERT: ON CONFLICT DO UPDATE)
--   - Пересчитывает AVG(rating) и COUNT(*) для rated_user_id
--   - Обновляет profiles.rating и profiles.ratings_count
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

    -- 4. Проверить, что оцениваемый пользователь существует
    IF NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE id = p_rated_user_id
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    -- 5. UPSERT оценки (один пользователь — одна оценка на задание)
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

    -- 6. Пересчитать средний рейтинг и количество оценок для rated_user_id
    SELECT
        COALESCE(ROUND(AVG(rating)::numeric, 1), 0),
        COUNT(*)::int
    INTO v_new_avg, v_new_count
    FROM public.ratings
    WHERE rated_user_id = p_rated_user_id;

    -- 7. Обновить профиль пользователя
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
-- RPC 4: update_job_status_atomic
-- Атомарно обновляет статус задания с проверкой допустимых переходов (state machine).
-- Допустимые переходы:
--   active  → in_progress, completed, cancelled
--   in_progress → completed, cancelled
--   open    → cancelled
--   completed → open (переоткрытие, если есть свободные места)
--   cancelled → open (переоткрытие)
-- Проверяет, что пользователь — владелец задания.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.update_job_status_atomic(
    p_job_id uuid,
    p_new_status text,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current_status text;
    v_employer_id uuid;
    v_allowed boolean;
BEGIN
    -- 1. Получить текущий статус и владельца задания с блокировкой
    SELECT status, employer_id
    INTO v_current_status, v_employer_id
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

    -- 3. Проверить допустимость перехода (state machine)
    v_allowed := false;

    -- active → in_progress, completed, cancelled
    IF v_current_status = 'active' AND p_new_status IN ('in_progress', 'completed', 'cancelled') THEN
        v_allowed := true;
    END IF;

    -- in_progress → completed, cancelled
    IF v_current_status = 'in_progress' AND p_new_status IN ('completed', 'cancelled') THEN
        v_allowed := true;
    END IF;

    -- open → cancelled
    IF v_current_status = 'open' AND p_new_status = 'cancelled' THEN
        v_allowed := true;
    END IF;

    -- completed → open (переоткрытие)
    IF v_current_status = 'completed' AND p_new_status = 'open' THEN
        v_allowed := true;
    END IF;

    -- cancelled → open (переоткрытие)
    IF v_current_status = 'cancelled' AND p_new_status = 'open' THEN
        v_allowed := true;
    END IF;

    -- Переход на тот же статус — допустим (идемпотентность)
    IF v_current_status = p_new_status THEN
        v_allowed := true;
    END IF;

    IF NOT v_allowed THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format(
                'Недопустимый переход статуса: ''%s'' → ''%s''',
                v_current_status, p_new_status
            ),
            'code', 'invalid_transition',
            'current_status', v_current_status
        );
    END IF;

    -- 4. Обновить статус
    UPDATE public.jobs
    SET status = p_new_status,
        updated_at = now()
    WHERE id = p_job_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Статус задания обновлён',
        'old_status', v_current_status,
        'new_status', p_new_status
    );
END;
$$;


-- ============================================================================
-- RPC 5: resolve_user_atomic
-- Принимает UUID пользователя, возвращает JSON с базовой информацией.
-- Замена для N+1 запросов к profiles.
-- Возвращает: id, full_name, photo_url, avatar_url, rating, role
-- Если пользователь не найден — возвращает ошибку.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.resolve_user_atomic(
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_profile record;
BEGIN
    -- 1. Найти пользователя
    SELECT id, full_name, photo_url, avatar_url, rating, role
    INTO v_profile
    FROM public.profiles
    WHERE id = p_user_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    -- 2. Вернуть базовую информацию
    RETURN jsonb_build_object(
        'success', true,
        'data', jsonb_build_object(
            'id', v_profile.id,
            'full_name', v_profile.full_name,
            'photo_url', COALESCE(v_profile.photo_url, v_profile.avatar_url, ''),
            'avatar_url', COALESCE(v_profile.avatar_url, v_profile.photo_url, ''),
            'rating', COALESCE(v_profile.rating, 0),
            'role', v_profile.role
        )
    );
END;
$$;


-- ============================================================================
-- Права доступа: REVOKE от анонимов, GRANT для authenticated и service_role
-- ============================================================================

-- RPC 1: withdraw_application_atomic
REVOKE EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) TO authenticated, service_role;

-- RPC 2: cancel_worker_atomic
REVOKE EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) TO authenticated, service_role;

-- RPC 3: rate_user_atomic
REVOKE EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) TO authenticated, service_role;

-- RPC 4: update_job_status_atomic
REVOKE EXECUTE ON FUNCTION public.update_job_status_atomic(uuid, text, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.update_job_status_atomic(uuid, text, uuid) TO authenticated, service_role;

-- RPC 5: resolve_user_atomic
REVOKE EXECUTE ON FUNCTION public.resolve_user_atomic(uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.resolve_user_atomic(uuid) TO authenticated, service_role;

COMMIT;

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
