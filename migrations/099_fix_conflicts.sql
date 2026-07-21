-- 099_fix_conflicts.sql
-- Патч: восстанавливает правильные сигнатуры после миграции 091.
-- Применять ПОСЛЕ всех остальных миграций (076-096).

-- 1. accept_application(p_job_id uuid, p_app_id uuid)
DROP FUNCTION IF EXISTS public.accept_application(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.accept_application(p_job_id uuid, p_app_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_cw int; v_mw int; v_js text; v_nc int; v_ns text; v_eid uuid; v_wid uuid; v_as text;
BEGIN
    SELECT current_workers, max_workers, status, employer_id INTO v_cw, v_mw, v_js, v_eid
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    IF v_js NOT IN ('open','active') THEN RETURN jsonb_build_object('success',false,'error','job_not_open','code','job_not_open'); END IF;
    IF v_cw >= v_mw THEN RETURN jsonb_build_object('success',false,'error','no_slots','code','no_slots'); END IF;
    SELECT status, worker_id INTO v_as, v_wid FROM public.applications WHERE id=p_app_id AND job_id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','app_not_found','code','not_found'); END IF;
    IF v_as NOT IN ('pending','rejected') THEN RETURN jsonb_build_object('success',false,'error','bad_status','code','bad_status'); END IF;
    UPDATE public.applications SET status='accepted', updated_at=now() WHERE id=p_app_id AND job_id=p_job_id;
    v_nc := v_cw + 1; v_ns := CASE WHEN v_nc >= v_mw THEN 'completed' ELSE 'open' END;
    UPDATE public.jobs SET status=v_ns, current_workers=v_nc, updated_at=now() WHERE id=p_job_id;
    UPDATE public.applications SET status='rejected', updated_at=now() WHERE job_id=p_job_id AND status='pending' AND id!=p_app_id;
    RETURN jsonb_build_object('success',true,'current_workers',v_nc,'job_status',v_ns,'worker_id',v_wid,'job_id',p_job_id);
END; $$;
REVOKE EXECUTE ON FUNCTION public.accept_application(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.accept_application(uuid,uuid) TO authenticated, service_role;

-- 2. reject_application(p_job_id uuid, p_app_id uuid)
DROP FUNCTION IF EXISTS public.reject_application(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eid uuid; v_wid uuid; v_cs text; v_cw int; v_mw int; v_js text; v_nw int; v_ns text;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    SELECT status, worker_id INTO v_cs, v_wid FROM public.applications WHERE id=p_app_id AND job_id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','app_not_found','code','not_found'); END IF;
    IF v_cs='rejected' THEN RETURN jsonb_build_object('success',false,'error','already_rejected','code','already_rejected'); END IF;
    UPDATE public.applications SET status='rejected', updated_at=now() WHERE id=p_app_id AND job_id=p_job_id;
    IF v_cs='accepted' THEN
        SELECT current_workers, max_workers, status INTO v_cw, v_mw, v_js FROM public.jobs WHERE id=p_job_id;
        v_nw := GREATEST(v_cw-1,0); v_ns := CASE WHEN v_nw=0 AND v_js='completed' THEN 'open' ELSE v_js END;
        UPDATE public.jobs SET status=v_ns, current_workers=v_nw, updated_at=now() WHERE id=p_job_id;
    END IF;
    RETURN jsonb_build_object('success',true,'worker_id',v_wid,'job_id',p_job_id);
END; $$;
REVOKE EXECUTE ON FUNCTION public.reject_application(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.reject_application(uuid,uuid) TO authenticated, service_role;

-- 3. apply_job_atomic: версия из 088 (с проверкой expires_at)
DROP FUNCTION IF EXISTS public.apply_job_atomic(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.apply_job_atomic(p_job_id uuid, p_worker_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_mw int; v_cw int; v_st text; v_eid uuid; v_exp timestamptz; v_aid uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id, expires_at
    INTO v_mw, v_cw, v_st, v_eid, v_exp FROM public.jobs WHERE id=p_job_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','job_not_found','code','job_not_found'); END IF;
    IF v_st NOT IN ('open','active') THEN RETURN jsonb_build_object('success',false,'error','job_not_open','code','job_not_open'); END IF;
    IF v_exp IS NOT NULL AND v_exp < now() THEN RETURN jsonb_build_object('success',false,'error','job_expired','code','job_expired'); END IF;
    IF v_eid = p_worker_id THEN RETURN jsonb_build_object('success',false,'error','own_job','code','own_job'); END IF;
    IF EXISTS(SELECT 1 FROM public.blacklists WHERE user_id=v_eid AND blocked_user_id=p_worker_id)
    THEN RETURN jsonb_build_object('success',false,'error','blacklisted','code','blacklisted'); END IF;
    INSERT INTO public.applications (job_id, worker_id, status) VALUES (p_job_id, p_worker_id, 'pending')
    RETURNING id INTO v_aid;
    RETURN jsonb_build_object('success',true,'application_id',v_aid,'employer_id',v_eid);
EXCEPTION WHEN unique_violation THEN
    RETURN jsonb_build_object('success',false,'error','duplicate','code','duplicate');
END; $$;
REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.apply_job_atomic(uuid,uuid) TO authenticated, service_role;

-- 4. delete_job_cascade: версия из 086 (полная, с проверкой владельца)
DROP FUNCTION IF EXISTS public.delete_job_cascade(uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eid uuid; va int; vs int; vp int; vf int; vi int; vn int;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found'); END IF;
    DELETE FROM public.applications WHERE job_id=p_job_id; GET DIAGNOSTICS va = ROW_COUNT;
    DELETE FROM public.job_skills WHERE job_id=p_job_id; GET DIAGNOSTICS vs = ROW_COUNT;
    DELETE FROM public.job_photos WHERE job_id=p_job_id; GET DIAGNOSTICS vp = ROW_COUNT;
    DELETE FROM public.favorites WHERE job_id=p_job_id; GET DIAGNOSTICS vf = ROW_COUNT;
    DELETE FROM public.invitations WHERE job_id=p_job_id; GET DIAGNOSTICS vi = ROW_COUNT;
    DELETE FROM public.notifications WHERE job_id=p_job_id; GET DIAGNOSTICS vn = ROW_COUNT;
    DELETE FROM public.jobs WHERE id=p_job_id;
    RETURN jsonb_build_object('success',true,'deleted_applications',va,'deleted_skills',vs,'deleted_photos',vp,'deleted_favorites',vf,'deleted_invitations',vi,'deleted_notifications',vn);
END; $$;
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;

-- 5. delete_user_cascade: версия из 092 (самая полная)
DROP FUNCTION IF EXISTS public.delete_user_cascade(uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.delete_user_cascade(p_user_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_role text; v_jid uuid;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id=p_user_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    IF v_role='employer' THEN FOR v_jid IN SELECT id FROM jobs WHERE employer_id=p_user_id LOOP PERFORM delete_job_cascade(v_jid); END LOOP; END IF;
    DELETE FROM applications WHERE worker_id=p_user_id;
    DELETE FROM notifications WHERE user_id=p_user_id;
    DELETE FROM notification_outbox WHERE user_id=p_user_id;
    DELETE FROM favorites WHERE user_id=p_user_id OR employer_id=p_user_id;
    DELETE FROM job_favorites WHERE user_id=p_user_id;
    DELETE FROM blacklists WHERE user_id=p_user_id OR blocked_user_id=p_user_id;
    DELETE FROM ratings WHERE rater_id=p_user_id OR rated_user_id=p_user_id;
    DELETE FROM invitations WHERE employer_id=p_user_id OR worker_id=p_user_id;
    DELETE FROM user_skills WHERE user_id=p_user_id;
    DELETE FROM push_subscriptions WHERE user_id=p_user_id;
    DELETE FROM messages WHERE sender_id=p_user_id OR receiver_id=p_user_id;
    DELETE FROM job_payments WHERE payer_id=p_user_id;
    DELETE FROM _archive_contact_payments WHERE user_id=p_user_id;
    UPDATE audit_log SET user_id=NULL WHERE user_id=p_user_id;
    DELETE FROM profiles WHERE id=p_user_id;
    RETURN jsonb_build_object('success',true,'deleted_user_id',p_user_id,'role',v_role);
END; $$;
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;
