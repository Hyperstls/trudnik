-- 151: worker completion confirmation.
--
-- Accepted workers can mark their work as completed. This is a signal to the
-- employer (who still completes the job via force_complete_job); it does not
-- change job status by itself. Nullable, additive migration.

ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS worker_completed_at timestamp with time zone;

CREATE OR REPLACE FUNCTION public.worker_confirm_completion(
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
    v_status text;
    v_job_id uuid;
    v_completed_at timestamp with time zone;
BEGIN
    SELECT worker_id, status, job_id, worker_completed_at
      INTO v_worker_id, v_status, v_job_id, v_completed_at
      FROM public.applications
     WHERE id = p_application_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик не найден', 'code', 'not_found');
    END IF;

    IF v_worker_id <> p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Это не ваш отклик', 'code', 'not_worker');
    END IF;

    IF v_status <> 'accepted' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик не принят', 'code', 'invalid_status');
    END IF;

    IF v_completed_at IS NULL THEN
        UPDATE public.applications
           SET worker_completed_at = now(),
               updated_at = now()
         WHERE id = p_application_id;
    END IF;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Выполнение отмечено',
        'job_id', v_job_id,
        'worker_completed_at', COALESCE(v_completed_at, now())
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.worker_confirm_completion(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.worker_confirm_completion(uuid, uuid)
    TO authenticated, service_role, trudnik_dj;
