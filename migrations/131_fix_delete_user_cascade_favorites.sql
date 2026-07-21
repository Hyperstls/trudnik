-- Migration 131: Fix delete_user_cascade — sync column names with actual schema
--
-- PROBLEM: delete_user_cascade referenced columns that don't match the real schema:
--   favorites.employer_id   -> favorites.target_id
--   ratings.rater_id        -> ratings.rater_user_id
--   messages.receiver_id    -> (no such column; messages has only sender_id + application_id)
--   job_payments.payer_id   -> job_payments.employer_id
--   _archive_contact_payments.user_id -> .employer_id / .worker_id
-- Admin user deletion failed: 400 "column ... does not exist".
--
-- FIX: recreate the function with the correct columns, schema-qualified (public.*),
-- SET search_path = pg_catalog, public. Idempotent.

CREATE OR REPLACE FUNCTION public.delete_user_cascade(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_role text;
    v_jid uuid;
BEGIN
    SELECT role INTO v_role FROM public.profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'not_found', 'code', 'not_found');
    END IF;

    IF v_role = 'employer' THEN
        FOR v_jid IN SELECT id FROM public.jobs WHERE employer_id = p_user_id LOOP
            PERFORM public.delete_job_cascade(v_jid);
        END LOOP;
    END IF;

    DELETE FROM public.applications          WHERE worker_id        = p_user_id;
    DELETE FROM public.notifications         WHERE user_id          = p_user_id;
    DELETE FROM public.notification_outbox   WHERE user_id          = p_user_id;
    DELETE FROM public.favorites             WHERE user_id          = p_user_id
                                                  OR target_id      = p_user_id;
    DELETE FROM public.job_favorites         WHERE user_id          = p_user_id;
    DELETE FROM public.blacklists            WHERE user_id          = p_user_id
                                                  OR blocked_user_id = p_user_id;
    DELETE FROM public.ratings               WHERE rater_user_id    = p_user_id
                                                  OR rated_user_id  = p_user_id;
    DELETE FROM public.invitations           WHERE employer_id      = p_user_id
                                                  OR worker_id      = p_user_id;
    DELETE FROM public.user_skills           WHERE user_id          = p_user_id;
    DELETE FROM public.push_subscriptions    WHERE user_id          = p_user_id;
    DELETE FROM public.messages              WHERE sender_id        = p_user_id;
    DELETE FROM public.job_payments          WHERE employer_id      = p_user_id;
    DELETE FROM public._archive_contact_payments WHERE employer_id  = p_user_id
                                                  OR worker_id      = p_user_id;
    UPDATE public.audit_log SET user_id = NULL WHERE user_id = p_user_id;
    DELETE FROM public.profiles              WHERE id               = p_user_id;

    RETURN jsonb_build_object('success', true, 'deleted_user_id', p_user_id, 'role', v_role);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;
