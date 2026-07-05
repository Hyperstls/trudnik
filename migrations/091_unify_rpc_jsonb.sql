-- 091_unify_rpc_jsonb.sql
-- Унификация return type: замена RETURNS json → RETURNS jsonb для 5 RPC-функций.
-- jsonb — нативный тип PostgreSQL, эффективнее для хранения и обработки.
-- Логика функций НЕ меняется, только тип возврата и json_build_object → jsonb_build_object.

-- 1. accept_application
DROP FUNCTION IF EXISTS accept_application(uuid, uuid);
CREATE OR REPLACE FUNCTION accept_application(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_job_id uuid;
    v_worker_id uuid;
    v_employer_id uuid;
    v_status text;
    v_current_workers int;
    v_max_workers int;
BEGIN
    SELECT a.job_id, a.worker_id, j.employer_id, a.status
    INTO v_job_id, v_worker_id, v_employer_id, v_status
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    WHERE a.id = p_application_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик не найден', 'code', 'not_found');
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нет доступа', 'code', 'forbidden');
    END IF;

    IF v_status != 'pending' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик уже обработан', 'code', 'invalid_status');
    END IF;

    SELECT j.current_workers, j.max_workers
    INTO v_current_workers, v_max_workers
    FROM jobs j WHERE j.id = v_job_id;

    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нет свободных мест', 'code', 'no_slots');
    END IF;

    UPDATE applications SET status = 'accepted', updated_at = NOW()
    WHERE id = p_application_id AND status = 'pending';

    UPDATE jobs
    SET current_workers = current_workers + 1,
        status = CASE WHEN current_workers + 1 >= max_workers THEN 'completed' ELSE 'open' END,
        updated_at = NOW()
    WHERE id = v_job_id
    RETURNING status INTO v_status;

    RETURN jsonb_build_object(
        'success', true,
        'new_status', v_status,
        'worker_id', v_worker_id,
        'job_id', v_job_id
    );
END;
$$;

-- 2. reject_application
DROP FUNCTION IF EXISTS reject_application(uuid, uuid);
CREATE OR REPLACE FUNCTION reject_application(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_job_id uuid;
    v_worker_id uuid;
    v_employer_id uuid;
    v_status text;
BEGIN
    SELECT a.job_id, a.worker_id, j.employer_id, a.status
    INTO v_job_id, v_worker_id, v_employer_id, v_status
    FROM applications a
    JOIN jobs j ON j.id = a.job_id
    WHERE a.id = p_application_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик не найден', 'code', 'not_found');
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нет доступа', 'code', 'forbidden');
    END IF;

    IF v_status NOT IN ('pending', 'accepted') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Отклик уже обработан', 'code', 'invalid_status');
    END IF;

    IF v_status = 'accepted' THEN
        UPDATE jobs
        SET current_workers = GREATEST(current_workers - 1, 0),
            status = CASE WHEN current_workers - 1 < max_workers THEN 'open' ELSE status END,
            updated_at = NOW()
        WHERE id = v_job_id;
    END IF;

    UPDATE applications SET status = 'rejected', updated_at = NOW()
    WHERE id = p_application_id;

    RETURN jsonb_build_object(
        'success', true,
        'worker_id', v_worker_id,
        'job_id', v_job_id
    );
END;
$$;

-- 3. delete_job_cascade
DROP FUNCTION IF EXISTS delete_job_cascade(uuid);
CREATE OR REPLACE FUNCTION delete_job_cascade(p_job_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
BEGIN
    DELETE FROM applications WHERE job_id = p_job_id;
    DELETE FROM job_favorites WHERE job_id = p_job_id;
    DELETE FROM job_payments WHERE job_id = p_job_id;
    DELETE FROM invitations WHERE job_id = p_job_id;
    DELETE FROM jobs WHERE id = p_job_id;
    RETURN jsonb_build_object('success', true, 'deleted_job_id', p_job_id);
END;
$$;

-- 4. delete_user_cascade (логика расширена в 092)
DROP FUNCTION IF EXISTS delete_user_cascade(uuid);
CREATE OR REPLACE FUNCTION delete_user_cascade(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_role text;
    v_job_id uuid;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Пользователь не найден', 'code', 'not_found');
    END IF;

    IF v_role = 'employer' THEN
        FOR v_job_id IN SELECT id FROM jobs WHERE employer_id = p_user_id LOOP
            PERFORM delete_job_cascade(v_job_id);
        END LOOP;
    END IF;

    DELETE FROM applications WHERE worker_id = p_user_id;
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM notification_outbox WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE user_id = p_user_id OR employer_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE user_id = p_user_id OR blocked_user_id = p_user_id;
    DELETE FROM ratings WHERE rater_id = p_user_id OR rated_user_id = p_user_id;
    DELETE FROM invitations WHERE employer_id = p_user_id OR worker_id = p_user_id;
    DELETE FROM user_skills WHERE user_id = p_user_id;
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;
    DELETE FROM messages WHERE sender_id = p_user_id OR receiver_id = p_user_id;
    DELETE FROM job_payments WHERE payer_id = p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id = p_user_id;

    UPDATE audit_log SET user_id = NULL WHERE user_id = p_user_id;

    DELETE FROM profiles WHERE id = p_user_id;

    RETURN jsonb_build_object('success', true, 'deleted_user_id', p_user_id, 'role', v_role);
END;
$$;

-- 5. apply_job_atomic
DROP FUNCTION IF EXISTS apply_job_atomic(uuid, uuid);
CREATE OR REPLACE FUNCTION apply_job_atomic(p_job_id uuid, p_worker_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_job jobs%ROWTYPE;
    v_existing_id uuid;
    v_blacklisted boolean;
    v_worker_role text;
BEGIN
    SELECT role INTO v_worker_role FROM profiles WHERE id = p_worker_id;
    IF v_worker_role IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'Пользователь не найден', 'code', 'user_not_found');
    END IF;
    IF v_worker_role != 'worker' THEN
        RETURN jsonb_build_object('success', false, 'error', 'Только работники могут откликаться', 'code', 'not_worker');
    END IF;

    SELECT * INTO v_job FROM jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_job.status != 'open' THEN
        RETURN jsonb_build_object('success', false, 'error', 'На это задание нельзя откликаться', 'code', 'job_not_open');
    END IF;

    IF v_job.employer_id = p_worker_id THEN
        RETURN jsonb_build_object('success', false, 'error', 'Нельзя откликаться на своё задание', 'code', 'own_job');
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM blacklists
        WHERE user_id = v_job.employer_id AND blocked_user_id = p_worker_id
    ) INTO v_blacklisted;
    IF v_blacklisted THEN
        RETURN jsonb_build_object('success', false, 'error', 'Работодатель добавил вас в чёрный список', 'code', 'blacklisted');
    END IF;

    SELECT id INTO v_existing_id FROM applications
    WHERE job_id = p_job_id AND worker_id = p_worker_id;
    IF FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Вы уже откликались на это задание', 'code', 'duplicate');
    END IF;

    IF v_job.current_workers >= v_job.max_workers THEN
        RETURN jsonb_build_object('success', false, 'error', 'Места заполнены', 'code', 'no_slots');
    END IF;

    INSERT INTO applications (job_id, worker_id, status, created_at, updated_at)
    VALUES (p_job_id, p_worker_id, 'pending', NOW(), NOW());

    RETURN jsonb_build_object(
        'success', true,
        'employer_id', v_job.employer_id,
        'job_id', p_job_id
    );
END;
$$;

GRANT EXECUTE ON FUNCTION accept_application(uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION reject_application(uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION delete_job_cascade(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION delete_user_cascade(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION apply_job_atomic(uuid, uuid) TO service_role;
