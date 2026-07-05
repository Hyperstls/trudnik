-- 092_fix_delete_user_cascade.sql
-- Расширенная версия delete_user_cascade: полная очистка всех связанных данных.
-- Для employer — каскадное удаление заданий через delete_job_cascade.
-- Для audit_log — обнуление user_id (не удаление записи).

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

    -- 1. Для employer — каскадно удалить все задания
    IF v_role = 'employer' THEN
        FOR v_job_id IN SELECT id FROM jobs WHERE employer_id = p_user_id LOOP
            PERFORM delete_job_cascade(v_job_id);
        END LOOP;
    END IF;

    -- 2. Удалить заявки работника
    DELETE FROM applications WHERE worker_id = p_user_id;

    -- 3. Удалить уведомления
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM notification_outbox WHERE user_id = p_user_id;

    -- 4. Удалить избранное
    DELETE FROM favorites WHERE user_id = p_user_id OR employer_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;

    -- 5. Удалить чёрные списки
    DELETE FROM blacklists WHERE user_id = p_user_id OR blocked_user_id = p_user_id;

    -- 6. Удалить рейтинги
    DELETE FROM ratings WHERE rater_id = p_user_id OR rated_user_id = p_user_id;

    -- 7. Удалить приглашения
    DELETE FROM invitations WHERE employer_id = p_user_id OR worker_id = p_user_id;

    -- 8. Удалить навыки
    DELETE FROM user_skills WHERE user_id = p_user_id;

    -- 9. Удалить push-подписки
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;

    -- 10. Удалить сообщения
    DELETE FROM messages WHERE sender_id = p_user_id OR receiver_id = p_user_id;

    -- 11. Удалить платежи
    DELETE FROM job_payments WHERE payer_id = p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id = p_user_id;

    -- 12. Обнулить audit_log (сохранить историю действий)
    UPDATE audit_log SET user_id = NULL WHERE user_id = p_user_id;

    -- 13. Удалить профиль
    DELETE FROM profiles WHERE id = p_user_id;

    RETURN jsonb_build_object('success', true, 'deleted_user_id', p_user_id, 'role', v_role);
END;
$$;

GRANT EXECUTE ON FUNCTION delete_user_cascade(uuid) TO service_role;
