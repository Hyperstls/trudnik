-- ============================================================================
-- Миграция 062: Объединённые атомарные RPC Фазы 2 (единый скрипт)
-- Дата: 2026-06-22
-- 
-- ИНСТРУКЦИЯ ПО ПРИМЕНЕНИЮ (русский):
--   1. Откройте pgAdmin (или любой SQL-клиент Supabase)
--   2. Подключитесь к целевой базе данных
--   3. Откройте этот файл и выполните его КАК ОДИН СКРИПТ целиком
--      (кнопка «Execute» / F5 в pgAdmin)
--   4. Убедитесь, что вывод не содержит ошибок
-- 
-- ЧТО ДЕЛАЕТ ЭТОТ СКРИПТ:
--   Объединяет ВСЕ атомарные RPC Фазы 2 в одной транзакции:
--     - Устанавливает права доступа (REVOKE + GRANT) для трёх RPC
--       нативной аутентификации из миграции 058 (login_user, register_user,
--       change_password) — сами функции уже созданы миграцией 058.
--     - Создаёт (CREATE OR REPLACE) 5 атомарных RPC из миграции 059:
--         withdraw_application_atomic, cancel_worker_atomic, rate_user_atomic,
--         update_job_status_atomic, resolve_user_atomic
--     - Создаёт (CREATE OR REPLACE) 3 атомарных RPC из миграции 061:
--         cancel_job_atomic, force_complete_job, accept_invitation_atomic
--     - Выдаёт права на все 8 RPC: REVOKE FROM anon, PUBLIC;
--       GRANT TO authenticated, service_role.
-- 
-- ИДЕМПОТЕНТНОСТЬ:
--   Все определения RPC используют CREATE OR REPLACE — скрипт можно
--   запускать повторно без побочных эффектов.
-- 
-- ЗАВИСИМОСТИ / САМОДОСТАТОЧНОСТЬ:
--   Скрипт НЕ требует предварительного применения других миграций.
--   Единственное предположение: таблицы profiles, jobs, applications,
--   invitations, ratings, notifications уже существуют в схеме public.
--   Три auth RPC (login_user, register_user, change_password) должны
--   быть созданы миграцией 058 — здесь для них только права доступа.
-- 
-- НЕ ВКЛЮЧЕНО (намеренно):
--   Миграции 053–057, 060 — они не относятся к атомарным RPC Фазы 2.
-- ============================================================================

BEGIN;

-- ============================================================================
-- Часть 1: Права доступа для нативных auth RPC (из миграции 058)
-- Сами функции login_user, register_user, change_password создаются
-- миграцией 058. Здесь только REVOKE + GRANT EXECUTE.
-- ============================================================================

-- RPC: login_user — аутентификация пользователя по email и паролю
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

-- RPC: register_user — регистрация нового пользователя
REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;

-- RPC: change_password — смена пароля с проверкой старого
REVOKE EXECUTE ON FUNCTION change_password(uuid, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION change_password(uuid, text, text) TO authenticated, service_role;


-- ============================================================================
-- Часть 2: Атомарные RPC из миграции 059 (Фаза 2, Группа 2A)
-- ============================================================================

-- ============================================================================
-- RPC 2.1: withdraw_application_atomic
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
-- RPC 2.2: cancel_worker_atomic
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
-- RPC 2.3: rate_user_atomic
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
-- RPC 2.4: update_job_status_atomic
-- Атомарно обновляет статус задания с проверкой допустимых переходов
-- (state machine).
-- Допустимые переходы:
--   active      → in_progress, completed, cancelled
--   in_progress → completed, cancelled
--   open        → cancelled
--   completed   → open (переоткрытие, если есть свободные места)
--   cancelled   → open (переоткрытие)
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
-- RPC 2.5: resolve_user_atomic
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
-- Часть 3: Атомарные RPC из миграции 061 (Фаза 2 — завершение)
-- ============================================================================

-- ============================================================================
-- RPC 3.1: cancel_job_atomic
-- Атомарно отменяет задание:
--   - Проверяет, что пользователь — владелец задания
--   - Блокирует строку задания (FOR UPDATE)
--   - Если задание completed и есть accepted-отклики — отказывает
--   - Обновляет статус задания на 'cancelled'
--   - Массово переводит все pending-отклики в 'rejected'
--   - Возвращает список worker_id для уведомлений (Python-side)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.cancel_job_atomic(
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
    v_accepted_count int;
    v_rejected_workers uuid[];
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

    -- 3. Если задание completed — проверить, что нет accepted-откликов
    IF v_status = 'completed' THEN
        SELECT count(*) INTO v_accepted_count
        FROM public.applications
        WHERE job_id = p_job_id AND status = 'accepted';

        IF v_accepted_count > 0 THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Невозможно отменить задание с принятыми работниками. Сначала попросите работников отозвать отклики.',
                'code', 'has_accepted_workers',
                'accepted_count', v_accepted_count
            );
        END IF;
    END IF;

    -- 4. Обновить статус задания на cancelled
    UPDATE public.jobs
    SET status = 'cancelled',
        updated_at = now()
    WHERE id = p_job_id;

    -- 5. Массово перевести pending-отклики в rejected
    --    и собрать worker_id для уведомлений
    WITH updated AS (
        UPDATE public.applications
        SET status = 'rejected'
        WHERE job_id = p_job_id AND status = 'pending'
        RETURNING worker_id
    )
    SELECT array_agg(DISTINCT worker_id)
    INTO v_rejected_workers
    FROM updated;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание отменено',
        'new_status', 'cancelled',
        'rejected_worker_ids', COALESCE(to_jsonb(v_rejected_workers), '[]'::jsonb)
    );
END;
$$;


-- ============================================================================
-- RPC 3.2: force_complete_job
-- Атомарно завершает задание:
--   - Проверяет, что пользователь — владелец задания
--   - Проверяет, что задание в статусе 'open'
--   - Массово отклоняет все pending-отклики (→ 'rejected')
--   - Переводит задание в 'completed'
--   - Возвращает список accepted worker_id для уведомлений (Python-side)
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

    -- 3. Проверить, что задание в статусе open
    IF v_status != 'open' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя завершить задание в статусе ''%s''. Ожидается open.', v_status),
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
-- RPC 3.3: accept_invitation_atomic
-- Атомарно принимает приглашение:
--   - Проверяет, что приглашение существует и в статусе 'pending'
--   - Проверяет, что пользователь — target (worker_id) приглашения
--   - Проверяет, что задание ещё открыто и есть свободные места
--   - Создаёт заявку со статусом 'accepted' (работодатель уже выбрал)
--   - Инкрементирует current_workers задания
--   - Если мест не осталось — переводит задание в 'completed'
--   - Обновляет статус приглашения на 'accepted'
--   - Возвращает employer_id для уведомлений (Python-side)
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

    -- 7. Создать заявку со статусом accepted (работодатель уже выбрал трудника)
    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (v_job_id, v_worker_id, 'accepted')
    ON CONFLICT (job_id, worker_id) DO UPDATE
        SET status = 'accepted'
    RETURNING id INTO v_application_id;

    -- 8. Инкрементировать current_workers
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

    -- 9. Обновить статус приглашения
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
-- Права доступа: REVOKE от анонимов, GRANT для authenticated и service_role
-- Для всех 8 атомарных RPC (Части 2 и 3)
-- ============================================================================

-- RPC: withdraw_application_atomic (059)
REVOKE EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) TO authenticated, service_role;

-- RPC: cancel_worker_atomic (059)
REVOKE EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) TO authenticated, service_role;

-- RPC: rate_user_atomic (059)
REVOKE EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) TO authenticated, service_role;

-- RPC: update_job_status_atomic (059)
REVOKE EXECUTE ON FUNCTION public.update_job_status_atomic(uuid, text, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.update_job_status_atomic(uuid, text, uuid) TO authenticated, service_role;

-- RPC: resolve_user_atomic (059)
REVOKE EXECUTE ON FUNCTION public.resolve_user_atomic(uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.resolve_user_atomic(uuid) TO authenticated, service_role;

-- RPC: cancel_job_atomic (061)
REVOKE EXECUTE ON FUNCTION public.cancel_job_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_job_atomic(uuid, uuid) TO authenticated, service_role;

-- RPC: force_complete_job (061)
REVOKE EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) TO authenticated, service_role;

-- RPC: accept_invitation_atomic (061)
REVOKE EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) TO authenticated, service_role;

COMMIT;

-- ============================================================================
-- ГОТОВО!
-- 
-- Итого в этом скрипте:
--   - 3 REVOKE/GRANT для auth RPC (login_user, register_user, change_password)
--   - 5 CREATE OR REPLACE + REVOKE/GRANT (RPC из миграции 059)
--   - 3 CREATE OR REPLACE + REVOKE/GRANT (RPC из миграции 061)
--   Всего: 8 атомарных RPC создано/обновлено, права выданы на все 11 функций.
-- ============================================================================