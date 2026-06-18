-- 048_atomic_apply_job.sql
-- Атомарная RPC-процедура для создания отклика (apply_job)
-- Устраняет TOCTOU race condition: проверка мест + вставка в одной транзакции
-- 
-- Использование из Python:
--   supabase_rpc('apply_job_atomic', {'p_job_id': job_id, 'p_worker_id': user_id}, use_admin=True)
--
-- Возвращает json с полями:
--   success (bool), error (text), code (text), employer_id (uuid)

BEGIN;

CREATE OR REPLACE FUNCTION apply_job_atomic(
    p_job_id uuid,
    p_worker_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job_status text;
    v_current_workers int;
    v_max_workers int;
    v_employer_id uuid;
    v_blacklisted boolean;
    v_already_applied boolean;
BEGIN
    -- 1. Заблокировать строку задания для предотвращения гонки данных
    SELECT status, current_workers, max_workers, employer_id
    INTO v_job_status, v_current_workers, v_max_workers, v_employer_id
    FROM jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 2. Проверить, что задание открыто для откликов
    IF v_job_status != 'open' THEN
        RETURN json_build_object(
            'success', false,
            'error', 'На это задание нельзя откликаться',
            'code', 'job_not_open'
        );
    END IF;

    -- 3. Проверить, что работник не откликается на собственное задание
    IF v_employer_id = p_worker_id THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Вы не можете откликаться на собственное задание',
            'code', 'own_job'
        );
    END IF;

    -- 4. Проверить, не заблокирован ли работник у этого работодателя
    SELECT EXISTS(
        SELECT 1 FROM blacklists
        WHERE user_id = v_employer_id AND blocked_user_id = p_worker_id
    ) INTO v_blacklisted;

    IF v_blacklisted THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Вы не можете откликнуться: работодатель добавил вас в чёрный список',
            'code', 'blacklisted'
        );
    END IF;

    -- 5. Проверить отсутствие дубликата отклика
    SELECT EXISTS(
        SELECT 1 FROM applications
        WHERE job_id = p_job_id AND worker_id = p_worker_id
    ) INTO v_already_applied;

    IF v_already_applied THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Вы уже откликались на это задание',
            'code', 'duplicate'
        );
    END IF;

    -- 6. КРИТИЧЕСКАЯ СЕКЦИЯ: проверить лимит мест (атомарно, под блокировкой FOR UPDATE)
    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object(
            'success', false,
            'error', format('Места в задании заполнены (максимум %s)', v_max_workers),
            'code', 'no_slots'
        );
    END IF;

    -- NOTE: current_workers инкрементируется триггером БД ON INSERT applications.
    -- Если триггер отсутствует, раскомментируйте строку ниже:
    -- UPDATE jobs SET current_workers = current_workers + 1 WHERE id = p_job_id;

    -- 7. Создать отклик (всё ещё под блокировкой строки задания)
    INSERT INTO applications (job_id, worker_id, status)
    VALUES (p_job_id, p_worker_id, 'pending');

    RETURN json_build_object(
        'success', true,
        'message', 'Отклик отправлен',
        'employer_id', v_employer_id
    );
END;
$$;

COMMIT;
