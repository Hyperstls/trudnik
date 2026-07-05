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
