-- 120_fix_accept_reject_for_update.sql
-- Исправление TOCTOU race condition в accept_application и reject_application
-- Добавление FOR UPDATE на applications для предотвращения параллельных изменений

BEGIN;

-- 1. accept_application — добавить FOR UPDATE на applications
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
    
    -- FOR UPDATE на applications для предотвращения race condition
    SELECT status, worker_id INTO v_as, v_wid FROM public.applications WHERE id=p_app_id AND job_id=p_job_id FOR UPDATE;
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

-- 2. reject_application — добавить FOR UPDATE на applications
DROP FUNCTION IF EXISTS public.reject_application(uuid, uuid) CASCADE;
CREATE OR REPLACE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_eid uuid; v_wid uuid; v_cs text; v_cw int; v_mw int; v_js text; v_nw int; v_ns text;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id=p_job_id;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','not_found','code','not_found'); END IF;
    
    -- FOR UPDATE на applications для предотвращения race condition
    SELECT status, worker_id INTO v_cs, v_wid FROM public.applications WHERE id=p_app_id AND job_id=p_job_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','app_not_found','code','not_found'); END IF;
    IF v_cs='rejected' THEN RETURN jsonb_build_object('success',false,'error','already_rejected','code','already_rejected'); END IF;
    
    UPDATE public.applications SET status='rejected', updated_at=now() WHERE id=p_app_id AND job_id=p_job_id;
    IF v_cs='accepted' THEN
        SELECT current_workers, max_workers, status INTO v_cw, v_mw, v_js FROM public.jobs WHERE id=p_job_id FOR UPDATE;
        v_nw := GREATEST(v_cw-1,0); v_ns := CASE WHEN v_nw=0 AND v_js='completed' THEN 'open' ELSE v_js END;
        UPDATE public.jobs SET status=v_ns, current_workers=v_nw, updated_at=now() WHERE id=p_job_id;
    END IF;
    RETURN jsonb_build_object('success',true,'worker_id',v_wid,'job_id',p_job_id);
END; $$;
REVOKE EXECUTE ON FUNCTION public.reject_application(uuid,uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.reject_application(uuid,uuid) TO authenticated, service_role;

COMMIT;
