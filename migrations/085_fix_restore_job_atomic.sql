-- ============================================================================
-- Миграция 085: Исправить restore_job_atomic
-- Проблема: UPDATE applications SET status = 'cancelled' нарушал CHECK-constraint,
-- т.к. допустимые статусы: ('pending', 'accepted', 'rejected', 'withdrawn')
-- Решение: rejected → pending (не cancelled!)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.restore_job_atomic(p_job_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_restored_count int;
    v_restored_worker_ids uuid[];
BEGIN
    SELECT employer_id, status INTO v_employer_id, v_status
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_employer_id != p_user_id
       AND current_setting('request.jwt.claim.app_role', true) NOT IN ('admin') THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    IF v_status != 'cancelled' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Можно восстановить только отменённое задание (текущий статус: %s)', v_status),
            'code', 'not_cancelled'
        );
    END IF;

    UPDATE public.jobs
    SET status = 'open', current_workers = 0, updated_at = now()
    WHERE id = p_job_id;

    -- Меняем rejected заявки на pending (НЕ cancelled — это нарушает CHECK!)
    WITH restored AS (
        UPDATE public.applications SET status = 'pending'
        WHERE job_id = p_job_id AND status = 'rejected'
        RETURNING id, worker_id
    )
    SELECT count(*), array_agg(DISTINCT worker_id)
    INTO v_restored_count, v_restored_worker_ids
    FROM restored;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание восстановлено',
        'job_status', 'open',
        'current_workers', 0,
        'restored_applications', v_restored_count,
        'restored_worker_ids', COALESCE(to_jsonb(v_restored_worker_ids), '[]'::jsonb)
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) TO authenticated, service_role;
