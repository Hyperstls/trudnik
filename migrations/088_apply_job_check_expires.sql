-- ============================================================================
-- Миграция 088: Добавить проверку expires_at в apply_job_atomic
-- Проблема: apply_job_atomic не проверяла expires_at, поэтому работники
-- могли откликаться на задания с истёкшим сроком.
-- Решение: добавить проверку v_expires_at < now() перед созданием отклика.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.apply_job_atomic(
    p_job_id uuid, p_worker_id uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_max_workers int;
    v_current_workers int;
    v_status text;
    v_employer_id uuid;
    v_expires_at timestamptz;
    v_app_id uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id, expires_at
      INTO v_max_workers, v_current_workers, v_status, v_employer_id, v_expires_at
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_status NOT IN ('open', 'active') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание недоступно для отклика', 'code', 'job_not_open');
    END IF;

    -- Проверка срока действия задания
    IF v_expires_at IS NOT NULL AND v_expires_at < now() THEN
        RETURN jsonb_build_object('success', false, 'error', 'Срок размещения задания истёк', 'code', 'job_expired');
    END IF;

    IF v_employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'own job', 'code', 'own_job');
    END IF;

    IF EXISTS (SELECT 1 FROM public.blacklists
               WHERE user_id = v_employer_id AND blocked_user_id = p_worker_id) THEN
        RETURN jsonb_build_object('success', false, 'error', 'blacklisted', 'code', 'blacklisted');
    END IF;

    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (p_job_id, p_worker_id, 'pending')
    RETURNING id INTO v_app_id;

    RETURN jsonb_build_object('success', true, 'application_id', v_app_id, 'employer_id', v_employer_id);
EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('success', false, 'error', 'duplicate', 'code', 'duplicate');
END;
$$;

REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;
