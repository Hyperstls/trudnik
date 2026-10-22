-- Migration 147: apply_job_atomic — отказ на отклик к заданию из прошлого
--
-- 2026-09: баг из эксплуатации — пользователь откликнулся на задание,
-- начавшееся полтора месяца назад (status='open', expires_at не задан).
-- Добавляем проверку date_time: если задание уже началось/прошло — 409
-- job_in_past с человекочитаемым сообщением.
--
-- Идемпотентна (CREATE OR REPLACE). Применение: вручную после деплоя
-- (MIGRATIONS_ENABLED=true python scripts/apply_migrations.py).

CREATE OR REPLACE FUNCTION public.apply_job_atomic(p_job_id uuid, p_worker_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_mw int; v_cw int; v_st text; v_eid uuid; v_exp timestamptz; v_dt timestamptz; v_aid uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id, expires_at, date_time
    INTO v_mw, v_cw, v_st, v_eid, v_exp, v_dt FROM public.jobs WHERE id=p_job_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('success',false,'error','job_not_found','code','job_not_found'); END IF;
    IF v_st NOT IN ('open','active') THEN RETURN jsonb_build_object('success',false,'error','job_not_open','code','job_not_open'); END IF;
    IF v_exp IS NOT NULL AND v_exp < now() THEN RETURN jsonb_build_object('success',false,'error','job_expired','code','job_expired'); END IF;
    -- 2026-09: задание уже началось/прошло по date_time — откликаться бессмысленно.
    -- Окно-грейс 24ч: задание «на сегодня» (date_time=now по умолчанию формы) —
    -- откликаться можно; явно прошедшие (напр. 1,5 месяца назад) — нельзя.
    IF v_dt IS NOT NULL AND v_dt < now() - interval '24 hours' THEN
        RETURN jsonb_build_object('success',false,'error','Это задание уже началось или прошло','code','job_in_past');
    END IF;
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

NOTIFY pgrst, 'reload schema';
