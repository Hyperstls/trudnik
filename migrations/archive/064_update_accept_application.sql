-- ============================================================================
-- Миграция 064: Обновление RPC accept_application — поддержка rejected→accepted
-- Дата: 2026-06-22
-- Контекст: Задача #17 Фазы 2 (HIGH) — перенос rejected→pending перехода
--   внутрь атомарной RPC accept_application.
-- 
-- ПРОБЛЕМА: В applications.py перед вызовом RPC accept_application выполнялся
--   отдельный PATCH rejected→pending. При сбое RPC после PATCH данные
--   оставались в несогласованном состоянии.
-- 
-- РЕШЕНИЕ: RPC теперь принимает заявки в статусах 'pending' И 'rejected'.
--   Промежуточный PATCH из Python-кода больше не нужен.
-- 
-- ИДЕМПОТЕНТНОСТЬ: CREATE OR REPLACE.
-- ============================================================================

BEGIN;

-- Обновлённый accept_application: принимает заявки в статусах pending и rejected
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

    -- 3. Принять отклик (теперь и из rejected, не только из pending)
    UPDATE applications
    SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status IN ('pending', 'rejected');

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

    RETURN json_build_object(
        'success', true,
        'message', 'Отклик принят',
        'current_workers', v_new_count,
        'job_status', v_new_status
    );
END;
$$;

-- Права доступа (идемпотентно)
REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

COMMIT;
