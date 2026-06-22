-- ============================================================================
-- Миграция 061: Недостающие атомарные RPC (Фаза 2 — завершение)
-- Дата: 2026-06-22
-- Контекст: Дополняет миграцию 059 тремя RPC, которые были пропущены:
--   RPC 1: cancel_job_atomic — атомарная отмена задания с проверкой accepted-откликов
--   RPC 2: force_complete_job — атомарный reject всех pending + установка completed
--   RPC 3: accept_invitation_atomic — атомарное принятие приглашения (apply + инкремент)
-- Зависит от: 059_add_refactoring_rpcs.sql, 058_add_native_auth.sql
-- Идемпотентна: CREATE OR REPLACE.
-- ============================================================================

BEGIN;

-- ============================================================================
-- RPC 1: cancel_job_atomic
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
-- RPC 2: force_complete_job
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
-- RPC 3: accept_invitation_atomic
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
-- ============================================================================

-- RPC 1: cancel_job_atomic
REVOKE EXECUTE ON FUNCTION public.cancel_job_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_job_atomic(uuid, uuid) TO authenticated, service_role;

-- RPC 2: force_complete_job
REVOKE EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) TO authenticated, service_role;

-- RPC 3: accept_invitation_atomic
REVOKE EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) TO authenticated, service_role;

COMMIT;
