-- CI fixture: roles referenced by RLS policies.
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE service_role NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;

--
-- PostgreSQL database dump
--

-- Dumped from database version 15.8
-- Dumped by pg_dump version 15.8

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: tiger; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA tiger;


--
-- Name: tiger_data; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA tiger_data;


--
-- Name: topology; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA topology;


--
-- Name: SCHEMA topology; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA topology IS 'PostGIS Topology schema';


--
-- Name: fuzzystrmatch; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS fuzzystrmatch WITH SCHEMA public;


--
-- Name: EXTENSION fuzzystrmatch; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION fuzzystrmatch IS 'determine similarities and distance between strings';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


--
-- Name: postgis_tiger_geocoder; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder WITH SCHEMA tiger;


--
-- Name: EXTENSION postgis_tiger_geocoder; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis_tiger_geocoder IS 'PostGIS tiger geocoder and reverse geocoder';


--
-- Name: postgis_topology; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis_topology WITH SCHEMA topology;


--
-- Name: EXTENSION postgis_topology; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgis_topology IS 'PostGIS topology spatial types and functions';


--
-- Name: accept_application(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.accept_application(p_job_id uuid, p_app_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
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


--
-- Name: accept_invitation_atomic(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.accept_invitation_atomic(p_invitation_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_job_id uuid;
    v_employer_id uuid;
    v_worker_id uuid;
    v_inv_status text;
    v_job_status text;
    v_current_workers int;
    v_max_workers int;
    v_new_count int;
    v_new_job_status text;
    v_application_id uuid;
    v_existing_app_status text;
BEGIN
    -- 1. Получить приглашение с блокировкой
    SELECT job_id, employer_id, worker_id, status
    INTO v_job_id, v_employer_id, v_worker_id, v_inv_status
    FROM public.invitations
    WHERE id = p_invitation_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Приглашение не найдено',
            'code', 'invitation_not_found'
        );
    END IF;

    -- 2. Проверить, что пользователь — целевой работник
    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Это приглашение адресовано другому пользователю',
            'code', 'not_target'
        );
    END IF;

    -- 3. Проверить, что приглашение в статусе pending
    IF v_inv_status != 'pending' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Приглашение уже %s', v_inv_status),
            'code', 'invitation_not_pending'
        );
    END IF;

    -- 4. Получить задание с блокировкой строки
    SELECT status, current_workers, max_workers
    INTO v_job_status, v_current_workers, v_max_workers
    FROM public.jobs
    WHERE id = v_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 5. Проверить, что задание открыто для откликов
    IF v_job_status != 'open' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Задание в статусе ''%s'' — нельзя принять приглашение', v_job_status),
            'code', 'job_not_open'
        );
    END IF;

    -- 6. Проверить наличие свободных мест
    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Все места заняты (%s из %s)', v_current_workers, v_max_workers),
            'code', 'no_slots'
        );
    END IF;

    -- 7. Проверить существующую заявку — нельзя перезаписать accepted/cancelled
    SELECT status INTO v_existing_app_status
    FROM public.applications
    WHERE job_id = v_job_id AND worker_id = v_worker_id;

    IF v_existing_app_status IS NOT NULL AND v_existing_app_status NOT IN ('pending', 'rejected') THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Невозможно принять приглашение: заявка в статусе ''%s''', v_existing_app_status),
            'code', 'application_not_modifiable'
        );
    END IF;

    -- 8. Создать заявку со статусом accepted (работодатель уже выбрал трудника)
    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (v_job_id, v_worker_id, 'accepted')
    ON CONFLICT (job_id, worker_id) DO UPDATE
        SET status = 'accepted'
    RETURNING id INTO v_application_id;

    -- 9. Инкрементировать current_workers
    v_new_count := v_current_workers + 1;
    IF v_new_count >= v_max_workers THEN
        v_new_job_status := 'completed';
    ELSE
        v_new_job_status := v_job_status;
    END IF;

    UPDATE public.jobs
    SET current_workers = v_new_count,
        status = v_new_job_status,
        updated_at = now()
    WHERE id = v_job_id;

    -- 10. Обновить статус приглашения
    UPDATE public.invitations
    SET status = 'accepted',
        responded_at = now()
    WHERE id = p_invitation_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Приглашение принято',
        'job_id', v_job_id,
        'employer_id', v_employer_id,
        'worker_id', v_worker_id,
        'application_id', v_application_id,
        'current_workers', v_new_count,
        'job_status', v_new_job_status
    );
END;
$$;


--
-- Name: apply_job_atomic(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.apply_job_atomic(p_job_id uuid, p_worker_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
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


--
-- Name: cancel_job_atomic(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cancel_job_atomic(p_job_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_accepted_count int;
    v_rejected_workers uuid[];
BEGIN
    SELECT employer_id, status
    INTO v_employer_id, v_status
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    IF v_status = 'completed' THEN
        SELECT count(*) INTO v_accepted_count
        FROM public.applications
        WHERE job_id = p_job_id AND status = 'accepted';

        IF v_accepted_count > 0 THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Невозможно отменить задание с принятыми работниками. Сначала попросите работников отозвать отклики.',
                'code', 'has_accepted_workers',
                'accepted_count', v_accepted_count
            );
        END IF;
    END IF;

    UPDATE public.jobs
    SET status = 'cancelled',
        updated_at = now()
    WHERE id = p_job_id;

    WITH updated AS (
        UPDATE public.applications
        SET status = 'rejected'
        WHERE job_id = p_job_id AND status = 'pending'
        RETURNING worker_id
    )
    SELECT array_agg(DISTINCT worker_id)
    INTO v_rejected_workers
    FROM updated;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание отменено',
        'new_status', 'cancelled',
        'rejected_worker_ids', COALESCE(to_jsonb(v_rejected_workers), '[]'::jsonb)
    );
END;
$$;


--
-- Name: cancel_worker_atomic(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cancel_worker_atomic(p_application_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_worker_id uuid;
    v_job_id uuid;
    v_app_status text;
    v_employer_id uuid;
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_workers int;
    v_new_job_status text;
    v_notification_id uuid;
BEGIN
    -- 1. Получить заявку с блокировкой строки
    SELECT worker_id, job_id, status
    INTO v_worker_id, v_job_id, v_app_status
    FROM public.applications
    WHERE id = p_application_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Заявка не найдена',
            'code', 'application_not_found'
        );
    END IF;

    -- 2. Проверить, что заявка в статусе accepted
    IF v_app_status != 'accepted' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя отменить исполнителя в статусе ''%s''', v_app_status),
            'code', 'invalid_status'
        );
    END IF;

    -- 3. Получить задание и проверить владельца
    SELECT employer_id, current_workers, max_workers, status
    INTO v_employer_id, v_current_workers, v_max_workers, v_job_status
    FROM public.jobs
    WHERE id = v_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 4. Проверить, что пользователь — владелец задания
    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    -- 5. Проверка 12-часового окна до начала задания
    IF EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = v_job_id
        AND date_time IS NOT NULL
        AND date_time - INTERVAL '12 hours' <= NOW()
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Отказ от задания невозможен менее чем за 12 часов до начала',
            'code', 'deadline_passed'
        );
    END IF;

    -- 6. Обновить статус заявки на cancelled
    UPDATE public.applications
    SET status = 'cancelled'
    WHERE id = p_application_id;

    -- 7. Уменьшить счётчик занятых мест
    v_new_workers := GREATEST(0, v_current_workers - 1);

    -- Если мест стало 0 и задание было completed/active — возвращаем в open
    IF v_new_workers = 0 AND v_job_status IN ('completed', 'active', 'in_progress') THEN
        v_new_job_status := 'open';
    ELSE
        v_new_job_status := v_job_status;
    END IF;

    UPDATE public.jobs
    SET current_workers = v_new_workers,
        status = v_new_job_status
    WHERE id = v_job_id;

    -- 8. Создать уведомление работнику
    INSERT INTO public.notifications (user_id, type, title, message, data, is_read)
    VALUES (
        v_worker_id,
        'worker_cancelled',
        'Заявка отменена',
        format('Работодатель отменил ваше участие в задании #%s', v_job_id),
        jsonb_build_object('job_id', v_job_id, 'application_id', p_application_id),
        false
    )
    RETURNING id INTO v_notification_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Исполнитель отменён',
        'new_status', 'cancelled',
        'current_workers', v_new_workers,
        'job_status', v_new_job_status,
        'notification_id', v_notification_id
    );
END;
$$;


--
-- Name: change_password(text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.change_password(p_email text, p_new_password text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_user_id uuid;
BEGIN
    SELECT p.id INTO v_user_id FROM public.profiles p
    WHERE lower(p.email) = lower(p_email);
    IF v_user_id IS NULL THEN
        RETURN false;
    END IF;
    UPDATE public.profiles
       SET password_hash = crypt(p_new_password, gen_salt('bf', 12)),
           password_changed_at = now()
     WHERE id = v_user_id;
    RETURN true;
END;
$$;


--
-- Name: change_password(uuid, text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.change_password(p_user_id uuid, p_old_password text, p_new_password text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE v_hash text;
BEGIN
    SELECT password_hash INTO v_hash FROM public.profiles WHERE id = p_user_id;
    IF v_hash IS NULL OR v_hash != crypt(p_old_password, v_hash) THEN
        RETURN false;
    END IF;
    UPDATE public.profiles SET password_hash = crypt(p_new_password, gen_salt('bf', 12)) WHERE id = p_user_id;
    RETURN true;
END;
$$;


--
-- Name: delete_job_cascade(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.delete_job_cascade(p_job_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_eid uuid; va int; vs int; vp int; vf int; vi int; vn int;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'not_found');
    END IF;

    DELETE FROM public.applications   WHERE job_id = p_job_id; GET DIAGNOSTICS va = ROW_COUNT;
    DELETE FROM public.job_skills     WHERE job_id = p_job_id; GET DIAGNOSTICS vs = ROW_COUNT;
    DELETE FROM public.job_photos     WHERE job_id = p_job_id; GET DIAGNOSTICS vp = ROW_COUNT;
    DELETE FROM public.job_favorites  WHERE job_id = p_job_id; GET DIAGNOSTICS vf = ROW_COUNT;  -- FIX: job_favorites (was: favorites)
    DELETE FROM public.invitations    WHERE job_id = p_job_id; GET DIAGNOSTICS vi = ROW_COUNT;
    DELETE FROM public.notifications  WHERE job_id = p_job_id; GET DIAGNOSTICS vn = ROW_COUNT;
    DELETE FROM public.jobs           WHERE id      = p_job_id;

    RETURN jsonb_build_object(
        'success', true,
        'deleted_applications', va,
        'deleted_skills', vs,
        'deleted_photos', vp,
        'deleted_favorites', vf,
        'deleted_invitations', vi,
        'deleted_notifications', vn
    );
END;
$$;


--
-- Name: delete_skill_cascade(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.delete_skill_cascade(p_skill_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_skill_name text;
    v_user_count int;
    v_job_count int;
BEGIN
    SELECT name INTO v_skill_name FROM public.skills WHERE id = p_skill_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Навык не найден', 'code', 'skill_not_found');
    END IF;

    DELETE FROM public.user_skills WHERE skill_id = p_skill_id;
    GET DIAGNOSTICS v_user_count = ROW_COUNT;

    DELETE FROM public.job_skills WHERE skill_id = p_skill_id;
    GET DIAGNOSTICS v_job_count = ROW_COUNT;

    DELETE FROM public.skills WHERE id = p_skill_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Навык удалён',
        'skill_name', v_skill_name,
        'affected_users', v_user_count,
        'affected_jobs', v_job_count
    );
END;
$$;


--
-- Name: delete_user_cascade(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.delete_user_cascade(p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
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


--
-- Name: expire_unfilled_jobs(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.expire_unfilled_jobs() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE v_count integer;
BEGIN
    UPDATE jobs
       SET status = 'expired', updated_at = now()
     WHERE status = 'open'
       AND date_time IS NOT NULL
       AND date_time < now()
       AND NOT EXISTS (
           SELECT 1 FROM applications WHERE applications.job_id = jobs.id
       );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;


--
-- Name: file_report(uuid, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.file_report(p_reported uuid, p_reason text DEFAULT ''::text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_reporter uuid;
    v_inserted int;
BEGIN
    v_reporter := (current_setting('request.jwt.claims', true)::json->>'user_id')::uuid;
    IF v_reporter IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'not_authenticated');
    END IF;
    IF v_reporter = p_reported THEN
        RETURN jsonb_build_object('ok', false, 'error', 'cannot_report_self');
    END IF;
    INSERT INTO user_reports (reporter_id, reported_id, reason)
    VALUES (v_reporter, p_reported, p_reason)
    ON CONFLICT (reporter_id, reported_id) DO NOTHING;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;
    RETURN jsonb_build_object('ok', true, 'created', v_inserted > 0);
END;
$$;


--
-- Name: force_complete_job(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.force_complete_job(p_job_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_accepted_workers uuid[];
BEGIN
    -- 1. Получить задание с блокировкой строки
    SELECT employer_id, status
    INTO v_employer_id, v_status
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    -- 2. Проверить, что пользователь — владелец задания
    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    -- 3. Проверить, что задание в допустимом статусе (open, active, in_progress)
    IF v_status NOT IN ('open', 'active', 'in_progress') THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Задание не может быть завершено в текущем статусе ''%s''', v_status),
            'code', 'invalid_status',
            'current_status', v_status
        );
    END IF;

    -- 4. Массово отклонить все pending-отклики
    UPDATE public.applications
    SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending';

    -- 5. Перевести задание в completed
    UPDATE public.jobs
    SET status = 'completed',
        updated_at = now()
    WHERE id = p_job_id;

    -- 6. Собрать accepted-работников для уведомлений
    SELECT array_agg(DISTINCT worker_id)
    INTO v_accepted_workers
    FROM public.applications
    WHERE job_id = p_job_id AND status = 'accepted';

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание завершено',
        'new_status', 'completed',
        'accepted_worker_ids', COALESCE(to_jsonb(v_accepted_workers), '[]'::jsonb)
    );
END;
$$;


--
-- Name: get_admin_dashboard_stats(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_admin_dashboard_stats() RETURNS json
    LANGUAGE plpgsql STABLE SECURITY DEFINER
    AS $$
DECLARE result JSON;
BEGIN
    SELECT json_build_object(
        'total_users', (SELECT COUNT(*) FROM profiles),
        'workers', (SELECT COUNT(*) FROM profiles WHERE role='worker'),
        'employers', (SELECT COUNT(*) FROM profiles WHERE role='employer'),
        'admins', (SELECT COUNT(*) FROM profiles WHERE role='admin'),
        'total_jobs', (SELECT COUNT(*) FROM jobs),
        'open_jobs', (SELECT COUNT(*) FROM jobs WHERE status='open'),
        'completed_jobs', (SELECT COUNT(*) FROM jobs WHERE status='completed'),
        'cancelled_jobs', (SELECT COUNT(*) FROM jobs WHERE status='cancelled'),
        'pending_verifications', (SELECT COUNT(*) FROM profiles WHERE verification_status='pending')
    ) INTO result;
    RETURN result;
END;
$$;


--
-- Name: get_job_stats(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_job_stats() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    _result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total', COUNT(*),
        'open', COUNT(*) FILTER (WHERE status = 'open'),
        'completed', COUNT(*) FILTER (WHERE status = 'completed'),
        'cancelled', COUNT(*) FILTER (WHERE status = 'cancelled')
    ) INTO _result
    FROM public.jobs;
    RETURN _result;
END;
$$;


--
-- Name: jobs_geom_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.jobs_geom_update() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
        NEW.geom := public.ST_SetSRID(public.ST_MakePoint(NEW.lng, NEW.lat), 4326);
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: jobs_search_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.jobs_search_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.organization_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.object_description, '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(NEW.detailed_description, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.work_type, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.address, '')), 'D');
    RETURN NEW;
END;
$$;


--
-- Name: login_user(text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.login_user(p_email text, p_password text) RETURNS TABLE(user_id uuid, role text, full_name text, email_verified boolean)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $_$
DECLARE
    v_id uuid;
    v_hash text;
    v_role text;
    v_name text;
    v_verified boolean;
BEGIN
    SELECT id, password_hash, role, full_name, email_verified
    INTO v_id, v_hash, v_role, v_name, v_verified
    FROM profiles
    WHERE LOWER(email) = LOWER(p_email)
    LIMIT 1;
    
    IF v_id IS NULL THEN
        RETURN;
    END IF;
    
    IF v_hash IS NULL OR v_hash != crypt(p_password, v_hash) THEN
        RETURN;
    END IF;
    
    -- Пере-хешировать если rounds < 12 (старые хеши $2a$06$ или $2b$06$)
    IF v_hash LIKE '$2a$06$%' OR v_hash LIKE '$2b$06$%' THEN
        UPDATE profiles SET password_hash = crypt(p_password, gen_salt('bf', 12)) WHERE id = v_id;
    END IF;
    
    RETURN QUERY SELECT v_id, v_role, v_name, COALESCE(v_verified, true);
END;
$_$;


--
-- Name: nearby_jobs(double precision, double precision, double precision); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.nearby_jobs(p_lat double precision, p_lng double precision, p_radius_meters double precision DEFAULT 5000) RETURNS TABLE(id uuid, employer_id uuid, organization_name text, object_description text, work_type character varying, address character varying, city character varying, lat double precision, lng double precision, date_time timestamp with time zone, payment_amount numeric, status character varying, max_workers integer, current_workers integer, created_at timestamp with time zone, distance_meters double precision)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_point public.geometry := public.ST_SetSRID(public.ST_MakePoint(p_lng, p_lat), 4326);
BEGIN
    RETURN QUERY
    SELECT
        j.id::uuid, j.employer_id::uuid,
        j.organization_name::text, j.object_description::text,
        j.work_type::varchar, j.address::varchar, j.city::varchar,
        j.lat::double precision, j.lng::double precision,
        j.date_time::timestamptz, j.payment_amount::numeric,
        j.status::varchar, j.max_workers::int, j.current_workers::int,
        j.created_at::timestamptz,
        public.ST_Distance(j.geom::public.geography, v_point::public.geography)::double precision AS distance_meters
    FROM public.jobs j
    WHERE j.geom IS NOT NULL
      AND j.status = 'open'
      AND public.ST_DWithin(j.geom::public.geography, v_point::public.geography, p_radius_meters)
    ORDER BY j.geom <-> v_point
    LIMIT 50;
END;
$$;


--
-- Name: pgrst_pre_request(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.pgrst_pre_request() RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
BEGIN
    -- no-op: claims читаются политиками напрямую из request.jwt.claims (миграция 125).
    -- Функция сохранена для совместимости с PGRST_DB_PRE_REQUEST; удалить после
    -- снятия env-переменной с сервиса PostgREST.
    RETURN;
END;
$$;


--
-- Name: profiles_search_update(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.profiles_search_update() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.full_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(
            (SELECT string_agg(s.name, ' ')
               FROM public.user_skills us
               JOIN public.skills s ON s.id = us.skill_id
              WHERE us.user_id = NEW.id), '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(NEW.bio, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.city, '')), 'D');
    RETURN NEW;
END;
$$;


--
-- Name: rate_user_atomic(uuid, uuid, uuid, integer, text, text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.rate_user_atomic(p_job_id uuid, p_rater_user_id uuid, p_rated_user_id uuid, p_rating integer, p_comment text DEFAULT ''::text, p_rating_type text DEFAULT 'worker'::text, p_target_type text DEFAULT 'worker'::text) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_new_avg numeric(3,1);
    v_new_count int;
BEGIN
    -- 1. Валидация рейтинга
    IF p_rating < 1 OR p_rating > 5 THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Рейтинг должен быть от 1 до 5',
            'code', 'invalid_rating'
        );
    END IF;

    -- 2. Нельзя оценить самого себя
    IF p_rater_user_id = p_rated_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Нельзя оценить самого себя',
            'code', 'self_rating'
        );
    END IF;

    -- 3. Проверить, что задание существует и завершено
    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = p_job_id AND status = 'completed'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оценить можно только завершённое задание',
            'code', 'job_not_completed'
        );
    END IF;

    -- 4. Проверка участия оценивающего в задании
    IF NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id
        AND worker_id = p_rater_user_id
        AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не участвовали в этом задании',
            'code', 'not_participant'
        );
    END IF;

    -- 5. Проверка участия оцениваемого в задании
    IF NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id
        AND worker_id = p_rated_user_id
        AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не участвовал в этом задании',
            'code', 'rated_not_participant'
        );
    END IF;

    -- 6. Проверить, что оцениваемый пользователь существует
    IF NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE id = p_rated_user_id
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    -- 7. UPSERT оценки (одна оценка на пару оценщик–оцениваемый в рамках задания)
    INSERT INTO public.ratings (
        job_id,
        rater_user_id,
        rated_user_id,
        rating,
        comment,
        rating_type,
        target_type,
        created_at,
        updated_at
    ) VALUES (
        p_job_id,
        p_rater_user_id,
        p_rated_user_id,
        p_rating,
        p_comment,
        p_rating_type,
        p_target_type,
        now(),
        now()
    )
    ON CONFLICT (rater_user_id, job_id, rated_user_id)
    DO UPDATE SET
        rating = EXCLUDED.rating,
        comment = EXCLUDED.comment,
        updated_at = now();

    -- 8. Пересчитать средний рейтинг и количество оценок для rated_user_id
    SELECT
        COALESCE(ROUND(AVG(rating)::numeric, 1), 0),
        COUNT(*)::int
    INTO v_new_avg, v_new_count
    FROM public.ratings
    WHERE rated_user_id = p_rated_user_id;

    -- 9. Обновить профиль пользователя
    UPDATE public.profiles
    SET rating = v_new_avg,
        ratings_count = v_new_count
    WHERE id = p_rated_user_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Оценка сохранена',
        'new_avg_rating', v_new_avg,
        'new_ratings_count', v_new_count
    );
END;
$$;


--
-- Name: recompute_profile_rating(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.recompute_profile_rating() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_rated_user_id uuid;
    v_avg_rating numeric;
    v_count integer;
BEGIN
    -- Определяем rated_user_id из NEW или OLD записи
    IF TG_OP = 'DELETE' THEN
        v_rated_user_id := OLD.rated_user_id;
    ELSE
        v_rated_user_id := NEW.rated_user_id;
    END IF;
    
    -- Пересчитываем средний рейтинг атомарно
    SELECT COALESCE(ROUND(AVG(rating)::numeric, 1), 0), COUNT(*)::int
    INTO v_avg_rating, v_count
    FROM public.ratings
    WHERE rated_user_id = v_rated_user_id;
    
    -- Обновляем профиль
    UPDATE public.profiles
    SET rating = v_avg_rating,
        ratings_count = v_count
    WHERE id = v_rated_user_id;
    
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$;


--
-- Name: register_user(text, text, text, text, boolean); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.register_user(p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'::text, p_worker_visibility boolean DEFAULT true) RETURNS uuid
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE v_user_id uuid;
BEGIN
    IF p_role NOT IN ('worker', 'employer') THEN
        RAISE EXCEPTION 'invalid_role';
    END IF;
    IF EXISTS (SELECT 1 FROM public.profiles WHERE LOWER(email) = LOWER(p_email)) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO public.profiles (id, email, password_hash, full_name, role, email_verified, worker_visibility)
    VALUES (gen_random_uuid(), LOWER(p_email), crypt(p_password, gen_salt('bf', 12)), p_full_name, p_role, FALSE, p_worker_visibility)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$;


--
-- Name: reject_application(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
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


--
-- Name: resolve_user_atomic(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.resolve_user_atomic(p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_profile record;
BEGIN
    SELECT id, full_name, photo_url, avatar_url, rating, role
    INTO v_profile
    FROM public.profiles
    WHERE id = p_user_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    RETURN jsonb_build_object(
        'success', true,
        'data', jsonb_build_object(
            'id', v_profile.id,
            'full_name', v_profile.full_name,
            'photo_url', COALESCE(v_profile.photo_url, v_profile.avatar_url, ''),
            'avatar_url', COALESCE(v_profile.avatar_url, v_profile.photo_url, ''),
            'rating', COALESCE(v_profile.rating, 0),
            'role', v_profile.role
        )
    );
END;
$$;


--
-- Name: restore_job_atomic(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.restore_job_atomic(p_job_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
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


--
-- Name: review_complaint(uuid, text, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.review_complaint(p_report_id uuid, p_action text, p_admin_id uuid DEFAULT NULL::uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_reported uuid;
BEGIN
    SELECT reported_id INTO v_reported FROM user_reports WHERE id = p_report_id;
    IF v_reported IS NULL THEN
        RETURN jsonb_build_object('ok', false, 'error', 'not_found');
    END IF;

    IF p_action = 'block' THEN
        UPDATE profiles
           SET suspended = true, suspended_reason = 'admin: complaint review', suspended_at = now()
         WHERE id = v_reported;
        UPDATE user_reports
           SET status = 'actioned', reviewed_by = p_admin_id, reviewed_at = now()
         WHERE id = p_report_id;
    ELSIF p_action = 'dismiss' THEN
        UPDATE user_reports
           SET status = 'dismissed', reviewed_by = p_admin_id, reviewed_at = now()
         WHERE id = p_report_id;
    ELSE
        RETURN jsonb_build_object('ok', false, 'error', 'bad_action');
    END IF;

    RETURN jsonb_build_object('ok', true, 'reported_id', v_reported);
END;
$$;


--
-- Name: suspend_user(uuid, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.suspend_user(p_user_id uuid, p_reason text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    UPDATE profiles
       SET suspended = true, suspended_reason = p_reason, suspended_at = now()
     WHERE id = p_user_id;
    RETURN FOUND;
END;
$$;


--
-- Name: sync_user_skills(uuid, uuid[]); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sync_user_skills(p_user_id uuid, p_skill_ids uuid[]) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE
    v_claims json;
    v_caller uuid;
    v_role   text;
BEGIN
    -- Проверка вызывающего: сам пользователь ИЛИ service_role.
    -- PostgREST v14 отдаёт claims одним JSON-GUC (миграция 124/125).
    v_claims := current_setting('request.jwt.claims', true)::json;
    v_caller := (v_claims->>'user_id')::uuid;
    v_role   := v_claims->>'role';
    IF v_role IS DISTINCT FROM 'service_role'
       AND (v_caller IS NULL OR v_caller <> p_user_id) THEN
        RAISE EXCEPTION 'forbidden: cannot sync skills of another user'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Удаляем связи, которых нет в новом массиве.
    -- '<> ALL' от пустого массива истинно для каждой строки → DELETE всех.
    DELETE FROM public.user_skills
    WHERE user_id = p_user_id
      AND skill_id <> ALL (COALESCE(p_skill_ids, '{}'::uuid[]));

    -- Вставляем новые связи; дубликаты (уже существующие) пропускаем,
    -- навыки, отсутствующие в справочнике skills, — тоже (старое поведение).
    INSERT INTO public.user_skills (user_id, skill_id)
    SELECT p_user_id, s
    FROM unnest(COALESCE(p_skill_ids, '{}'::uuid[])) AS s
    WHERE s IN (SELECT id FROM public.skills)
    ON CONFLICT DO NOTHING;
END;
$$;


--
-- Name: unsuspend_user(uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.unsuspend_user(p_user_id uuid) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    UPDATE profiles
       SET suspended = false, suspended_reason = NULL, suspended_at = NULL
     WHERE id = p_user_id;
    RETURN FOUND;
END;
$$;


--
-- Name: update_job_status_atomic(uuid, text, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_job_status_atomic(p_job_id uuid, p_new_status text, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
    v_current_status text;
    v_employer_id uuid;
    v_allowed boolean;
BEGIN
    SELECT status, employer_id
    INTO v_current_status, v_employer_id
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    v_allowed := false;

    IF v_current_status = 'active' AND p_new_status IN ('in_progress', 'completed', 'cancelled') THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'in_progress' AND p_new_status IN ('completed', 'cancelled') THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'open' AND p_new_status = 'cancelled' THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'completed' AND p_new_status = 'open' THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'cancelled' AND p_new_status = 'open' THEN
        v_allowed := true;
    END IF;

    IF v_current_status = p_new_status THEN
        v_allowed := true;
    END IF;

    IF NOT v_allowed THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Недопустимый переход статуса: ''%s'' → ''%s''', v_current_status, p_new_status),
            'code', 'invalid_transition',
            'current_status', v_current_status
        );
    END IF;

    UPDATE public.jobs
    SET status = p_new_status,
        updated_at = now()
    WHERE id = p_job_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Статус задания обновлён',
        'old_status', v_current_status,
        'new_status', p_new_status
    );
END;
$$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


--
-- Name: users_exceeding_reports(integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.users_exceeding_reports(p_threshold integer DEFAULT 3, p_hours integer DEFAULT 24) RETURNS TABLE(reported_id uuid, report_count bigint)
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
    SELECT r.reported_id, count(*)::bigint
    FROM user_reports r
    JOIN profiles p ON p.id = r.reported_id
    WHERE r.created_at >= now() - make_interval(hours => p_hours)
      AND p.suspended = false
    GROUP BY r.reported_id
    HAVING count(*) >= p_threshold;
$$;


--
-- Name: verify_via_messenger(uuid, text, text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.verify_via_messenger(p_user_id uuid, p_provider text, p_messenger_uid text DEFAULT NULL::text) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
    UPDATE profiles
       SET verification_status  = 'approved',
           verification_provider = p_provider,
           messenger_user_id    = p_messenger_uid,
           verified_at          = now()
     WHERE id = p_user_id;
    RETURN FOUND;
END;
$$;


--
-- Name: withdraw_application_atomic(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.withdraw_application_atomic(p_application_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
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


--
-- Name: worker_confirm_completion(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.worker_confirm_completion(p_application_id uuid, p_user_id uuid) RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
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


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _archive_contact_payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public._archive_contact_payments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employer_id uuid NOT NULL,
    worker_id uuid NOT NULL,
    job_id uuid NOT NULL,
    application_id uuid,
    amount integer DEFAULT 290 NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    transaction_id text DEFAULT ''::text,
    created_at timestamp with time zone DEFAULT now(),
    paid_at timestamp with time zone
);


--
-- Name: _migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public._migrations (
    filename text NOT NULL,
    applied_at timestamp with time zone DEFAULT now(),
    checksum text
);


--
-- Name: applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    worker_id uuid NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    contact_paid boolean DEFAULT false,
    contact_payment_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    worker_completed_at timestamp with time zone,
    CONSTRAINT applications_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'rejected'::character varying, 'withdrawn'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id bigint NOT NULL,
    user_id uuid,
    action character varying(100) NOT NULL,
    table_name character varying(100),
    record_id uuid,
    old_data jsonb,
    new_data jsonb,
    ip_address inet,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_log_id_seq OWNED BY public.audit_log.id;


--
-- Name: auth_group; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_group (
    id integer NOT NULL,
    name character varying(150) NOT NULL
);


--
-- Name: auth_group_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_group ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_group_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: auth_group_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_group_permissions (
    id bigint NOT NULL,
    group_id integer NOT NULL,
    permission_id integer NOT NULL
);


--
-- Name: auth_group_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_group_permissions ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_group_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: auth_permission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auth_permission (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    content_type_id integer NOT NULL,
    codename character varying(100) NOT NULL
);


--
-- Name: auth_permission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.auth_permission ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.auth_permission_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: blacklists; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blacklists (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    blocked_user_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: django_admin_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_admin_log (
    id integer NOT NULL,
    action_time timestamp with time zone NOT NULL,
    object_id text,
    object_repr character varying(200) NOT NULL,
    action_flag smallint NOT NULL,
    change_message text NOT NULL,
    content_type_id integer,
    user_id uuid NOT NULL,
    CONSTRAINT django_admin_log_action_flag_check CHECK ((action_flag >= 0))
);


--
-- Name: django_admin_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_admin_log ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_admin_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_content_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_content_type (
    id integer NOT NULL,
    app_label character varying(100) NOT NULL,
    model character varying(100) NOT NULL
);


--
-- Name: django_content_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_content_type ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_content_type_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_migrations (
    id bigint NOT NULL,
    app character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    applied timestamp with time zone NOT NULL
);


--
-- Name: django_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.django_migrations ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.django_migrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: django_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.django_session (
    session_key character varying(40) NOT NULL,
    session_data text NOT NULL,
    expire_date timestamp with time zone NOT NULL
);


--
-- Name: email_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_log (
    id bigint NOT NULL,
    notification_id uuid,
    user_id uuid NOT NULL,
    to_email text,
    subject text,
    template_name character varying(100),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    last_attempt_at timestamp with time zone,
    sent_at timestamp with time zone,
    error_message text,
    error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: email_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.email_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: email_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.email_log_id_seq OWNED BY public.email_log.id;


--
-- Name: employer_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employer_details (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    name text DEFAULT ''::text NOT NULL,
    description text,
    address text,
    city text,
    lat double precision,
    lng double precision,
    company_name character varying(255),
    inn character varying(12),
    is_self_employed boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: employer_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employer_subscriptions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employer_id uuid NOT NULL,
    tariff character varying(20) DEFAULT 'basic'::character varying NOT NULL,
    jobs_remaining integer DEFAULT 0,
    is_promoted boolean DEFAULT false,
    promoted_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT employer_subscriptions_tariff_check CHECK (((tariff)::text = ANY ((ARRAY['basic'::character varying, 'pro'::character varying, 'business'::character varying])::text[])))
);


--
-- Name: favorites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.favorites (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    target_id uuid NOT NULL,
    favorite_type text DEFAULT 'worker'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invitations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    employer_id uuid NOT NULL,
    worker_id uuid NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying,
    message text,
    created_at timestamp with time zone DEFAULT now(),
    responded_at timestamp with time zone,
    CONSTRAINT invitations_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'rejected'::character varying])::text[])))
);


--
-- Name: job_favorites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_favorites (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    job_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: job_payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_payments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    employer_id uuid NOT NULL,
    amount integer NOT NULL,
    tariff character varying(20) DEFAULT 'standard'::character varying,
    type character varying(30) DEFAULT 'publication'::character varying,
    status character varying(20) DEFAULT 'pending'::character varying,
    transaction_id character varying(255),
    paid_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT job_payments_amount_check CHECK ((amount >= 0))
);


--
-- Name: job_photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_photos (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    job_id uuid NOT NULL,
    photo_url text DEFAULT ''::text NOT NULL,
    order_num integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: job_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_skills (
    job_id uuid NOT NULL,
    skill_id uuid NOT NULL
);


--
-- Name: jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    employer_id uuid NOT NULL,
    organization_name text DEFAULT ''::text NOT NULL,
    org_description text DEFAULT ''::text NOT NULL,
    object_description text DEFAULT ''::text NOT NULL,
    work_type character varying(100) DEFAULT ''::character varying NOT NULL,
    detailed_description text DEFAULT ''::text NOT NULL,
    address character varying(500),
    city character varying(255),
    lat double precision,
    lng double precision,
    date_time timestamp with time zone DEFAULT now() NOT NULL,
    payment_amount numeric,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    max_workers integer DEFAULT 1,
    current_workers integer DEFAULT 0,
    tariff character varying(20) DEFAULT 'standard'::character varying,
    is_paid boolean DEFAULT false,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    preferred_religion text DEFAULT 'не важно'::text,
    search_vector tsvector,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_promoted boolean DEFAULT false,
    promoted_until timestamp with time zone,
    photo_urls text[] DEFAULT '{}'::text[] NOT NULL,
    geom public.geometry(Point,4326),
    is_remote boolean DEFAULT false NOT NULL,
    moderation_status text DEFAULT 'ok'::text NOT NULL,
    moderation_reason text,
    CONSTRAINT jobs_current_workers_check CHECK (((current_workers >= 0) AND (current_workers <= max_workers))),
    CONSTRAINT jobs_max_workers_check CHECK ((max_workers >= 1)),
    CONSTRAINT jobs_moderation_status_check CHECK ((moderation_status = ANY (ARRAY['ok'::text, 'review'::text, 'rejected'::text]))),
    CONSTRAINT jobs_payment_amount_check CHECK ((payment_amount >= (0)::numeric)),
    CONSTRAINT jobs_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'open'::character varying, 'active'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'cancelled'::character varying, 'paid'::character varying, 'expired'::character varying])::text[])))
);


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id bigint NOT NULL,
    sender_id uuid NOT NULL,
    application_id uuid,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    client_message_id uuid,
    attachment_url text,
    attachment_name text,
    attachment_mime text,
    attachment_size integer,
    read_at timestamp with time zone,
    edited_at timestamp with time zone,
    deleted_at timestamp with time zone
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.messages ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: monetization_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.monetization_settings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    key text NOT NULL,
    value text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: notification_outbox; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notification_outbox (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    body text,
    data jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone,
    status character varying(20) DEFAULT 'pending'::character varying,
    attempts integer DEFAULT 0,
    CONSTRAINT notification_outbox_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'sent'::character varying, 'failed'::character varying, 'skipped'::character varying])::text[])))
);

ALTER TABLE ONLY public.notification_outbox FORCE ROW LEVEL SECURITY;


--
-- Name: notification_outbox_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notification_outbox_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notification_outbox_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notification_outbox_id_seq OWNED BY public.notification_outbox.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    title text NOT NULL,
    message text,
    job_id uuid,
    application_id uuid,
    data jsonb DEFAULT '{}'::jsonb,
    is_read boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profiles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    role text DEFAULT 'worker'::text NOT NULL,
    full_name text DEFAULT ''::text NOT NULL,
    phone text,
    photo_url text,
    avatar_url text,
    age integer,
    bio text,
    city text,
    experience text,
    desired_payment numeric,
    verification_status text DEFAULT 'none'::text,
    verification_doc_url text,
    rating double precision DEFAULT 0,
    total_reviews integer DEFAULT 0,
    ratings_count integer DEFAULT 0,
    religion_id uuid,
    portfolio_link text DEFAULT ''::text,
    inn text DEFAULT ''::text,
    is_self_employed boolean DEFAULT false,
    email_public text DEFAULT ''::text,
    contact text,
    notification_prefs jsonb DEFAULT '{}'::jsonb,
    search_vector tsvector,
    email text,
    password_hash text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    email_verified boolean DEFAULT false,
    consented_at timestamp with time zone,
    password_changed_at timestamp with time zone DEFAULT now(),
    suspended boolean DEFAULT false NOT NULL,
    suspended_reason text,
    suspended_at timestamp with time zone,
    verification_provider text DEFAULT 'manual'::text,
    messenger_user_id text,
    verified_at timestamp with time zone,
    worker_visibility boolean DEFAULT true NOT NULL,
    acquisition jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT profiles_age_check CHECK (((age IS NULL) OR ((age >= 14) AND (age <= 120)))),
    CONSTRAINT profiles_email_check CHECK ((email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text)),
    CONSTRAINT profiles_inn_check CHECK (((inn IS NULL) OR (inn = ''::text) OR (inn ~ '^\d{10,12}$'::text))),
    CONSTRAINT profiles_role_check CHECK ((role = ANY (ARRAY['worker'::text, 'employer'::text, 'admin'::text])))
);


--
-- Name: push_subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.push_subscriptions (
    id bigint NOT NULL,
    user_id uuid NOT NULL,
    endpoint text NOT NULL,
    p256dh text NOT NULL,
    auth text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: push_subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.push_subscriptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: push_subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.push_subscriptions_id_seq OWNED BY public.push_subscriptions.id;


--
-- Name: ratings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ratings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    rated_user_id uuid NOT NULL,
    rater_user_id uuid NOT NULL,
    job_id uuid,
    rating_type character varying(20) NOT NULL,
    target_type character varying(20) NOT NULL,
    rating integer NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ratings_rating_check CHECK (((rating >= 1) AND (rating <= 5))),
    CONSTRAINT ratings_rating_type_check CHECK (((rating_type)::text = ANY ((ARRAY['worker'::character varying, 'employer'::character varying])::text[]))),
    CONSTRAINT ratings_target_type_check CHECK (((target_type)::text = ANY ((ARRAY['worker'::character varying, 'employer'::character varying])::text[])))
);


--
-- Name: receipts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.receipts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    contact_payment_id uuid,
    church_name text DEFAULT ''::text NOT NULL,
    church_inn text DEFAULT ''::text NOT NULL,
    service_description text DEFAULT ''::text NOT NULL,
    amount integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'sent'::text NOT NULL,
    receipt_json jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    resent_at timestamp with time zone,
    CONSTRAINT receipts_amount_check CHECK ((amount >= 0))
);


--
-- Name: religions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.religions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    id integer NOT NULL,
    version character varying(255) NOT NULL,
    applied_at timestamp with time zone DEFAULT now(),
    checksum text
);


--
-- Name: schema_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.schema_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: schema_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.schema_migrations_id_seq OWNED BY public.schema_migrations.id;


--
-- Name: site_pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.site_pages (
    slug text NOT NULL,
    title text DEFAULT ''::text NOT NULL,
    content text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.skills (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    sort_order integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: tariff_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tariff_settings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tariff_key character varying(30) NOT NULL,
    price integer NOT NULL,
    duration_days integer DEFAULT 30 NOT NULL,
    renewal_price integer,
    is_active boolean DEFAULT true,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_activity; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_activity (
    user_id uuid NOT NULL,
    day date NOT NULL
);


--
-- Name: user_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_reports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    reporter_id uuid NOT NULL,
    reported_id uuid NOT NULL,
    reason text DEFAULT ''::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status text DEFAULT 'new'::text NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone
);


--
-- Name: user_skills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_skills (
    user_id uuid NOT NULL,
    skill_id uuid NOT NULL
);


--
-- Name: audit_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ALTER COLUMN id SET DEFAULT nextval('public.audit_log_id_seq'::regclass);


--
-- Name: email_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_log ALTER COLUMN id SET DEFAULT nextval('public.email_log_id_seq'::regclass);


--
-- Name: notification_outbox id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_outbox ALTER COLUMN id SET DEFAULT nextval('public.notification_outbox_id_seq'::regclass);


--
-- Name: push_subscriptions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.push_subscriptions_id_seq'::regclass);


--
-- Name: schema_migrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations ALTER COLUMN id SET DEFAULT nextval('public.schema_migrations_id_seq'::regclass);


--
-- Name: _archive_contact_payments _archive_contact_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public._archive_contact_payments
    ADD CONSTRAINT _archive_contact_payments_pkey PRIMARY KEY (id);


--
-- Name: _migrations _migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public._migrations
    ADD CONSTRAINT _migrations_pkey PRIMARY KEY (filename);


--
-- Name: applications applications_job_id_worker_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_job_id_worker_id_key UNIQUE (job_id, worker_id);


--
-- Name: applications applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: auth_group auth_group_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_name_key UNIQUE (name);


--
-- Name: auth_group_permissions auth_group_permissions_group_id_permission_id_0cd325b0_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_permission_id_0cd325b0_uniq UNIQUE (group_id, permission_id);


--
-- Name: auth_group_permissions auth_group_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_pkey PRIMARY KEY (id);


--
-- Name: auth_group auth_group_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group
    ADD CONSTRAINT auth_group_pkey PRIMARY KEY (id);


--
-- Name: auth_permission auth_permission_content_type_id_codename_01ab375a_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_codename_01ab375a_uniq UNIQUE (content_type_id, codename);


--
-- Name: auth_permission auth_permission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_pkey PRIMARY KEY (id);


--
-- Name: blacklists blacklists_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blacklists
    ADD CONSTRAINT blacklists_pkey PRIMARY KEY (id);


--
-- Name: blacklists blacklists_user_id_blocked_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blacklists
    ADD CONSTRAINT blacklists_user_id_blocked_user_id_key UNIQUE (user_id, blocked_user_id);


--
-- Name: django_admin_log django_admin_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_pkey PRIMARY KEY (id);


--
-- Name: django_content_type django_content_type_app_label_model_76bd3d3b_uniq; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_app_label_model_76bd3d3b_uniq UNIQUE (app_label, model);


--
-- Name: django_content_type django_content_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_content_type
    ADD CONSTRAINT django_content_type_pkey PRIMARY KEY (id);


--
-- Name: django_migrations django_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_migrations
    ADD CONSTRAINT django_migrations_pkey PRIMARY KEY (id);


--
-- Name: django_session django_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_session
    ADD CONSTRAINT django_session_pkey PRIMARY KEY (session_key);


--
-- Name: email_log email_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_log
    ADD CONSTRAINT email_log_pkey PRIMARY KEY (id);


--
-- Name: employer_details employer_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employer_details
    ADD CONSTRAINT employer_details_pkey PRIMARY KEY (id);


--
-- Name: employer_details employer_details_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employer_details
    ADD CONSTRAINT employer_details_user_id_key UNIQUE (user_id);


--
-- Name: employer_subscriptions employer_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employer_subscriptions
    ADD CONSTRAINT employer_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: favorites favorites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_pkey PRIMARY KEY (id);


--
-- Name: favorites favorites_user_id_target_id_favorite_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT favorites_user_id_target_id_favorite_type_key UNIQUE (user_id, target_id, favorite_type);


--
-- Name: invitations invitations_job_id_worker_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_job_id_worker_id_key UNIQUE (job_id, worker_id);


--
-- Name: invitations invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT invitations_pkey PRIMARY KEY (id);


--
-- Name: job_favorites job_favorites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_favorites
    ADD CONSTRAINT job_favorites_pkey PRIMARY KEY (id);


--
-- Name: job_favorites job_favorites_user_id_job_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_favorites
    ADD CONSTRAINT job_favorites_user_id_job_id_key UNIQUE (user_id, job_id);


--
-- Name: job_payments job_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_payments
    ADD CONSTRAINT job_payments_pkey PRIMARY KEY (id);


--
-- Name: job_photos job_photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_photos
    ADD CONSTRAINT job_photos_pkey PRIMARY KEY (id);


--
-- Name: job_skills job_skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_skills
    ADD CONSTRAINT job_skills_pkey PRIMARY KEY (job_id, skill_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: monetization_settings monetization_settings_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monetization_settings
    ADD CONSTRAINT monetization_settings_key_key UNIQUE (key);


--
-- Name: monetization_settings monetization_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.monetization_settings
    ADD CONSTRAINT monetization_settings_pkey PRIMARY KEY (id);


--
-- Name: notification_outbox notification_outbox_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notification_outbox
    ADD CONSTRAINT notification_outbox_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);


--
-- Name: push_subscriptions push_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions
    ADD CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: push_subscriptions push_subscriptions_user_id_endpoint_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions
    ADD CONSTRAINT push_subscriptions_user_id_endpoint_key UNIQUE (user_id, endpoint);


--
-- Name: ratings ratings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_pkey PRIMARY KEY (id);


--
-- Name: ratings ratings_rater_job_rated_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT ratings_rater_job_rated_unique UNIQUE (rater_user_id, job_id, rated_user_id);


--
-- Name: receipts receipts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.receipts
    ADD CONSTRAINT receipts_pkey PRIMARY KEY (id);


--
-- Name: religions religions_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.religions
    ADD CONSTRAINT religions_name_key UNIQUE (name);


--
-- Name: religions religions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.religions
    ADD CONSTRAINT religions_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_version_key UNIQUE (version);


--
-- Name: site_pages site_pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site_pages
    ADD CONSTRAINT site_pages_pkey PRIMARY KEY (slug);


--
-- Name: skills skills_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_name_key UNIQUE (name);


--
-- Name: skills skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.skills
    ADD CONSTRAINT skills_pkey PRIMARY KEY (id);


--
-- Name: tariff_settings tariff_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tariff_settings
    ADD CONSTRAINT tariff_settings_pkey PRIMARY KEY (id);


--
-- Name: tariff_settings tariff_settings_tariff_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tariff_settings
    ADD CONSTRAINT tariff_settings_tariff_key_key UNIQUE (tariff_key);


--
-- Name: user_reports uq_user_reports_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reports
    ADD CONSTRAINT uq_user_reports_pair UNIQUE (reporter_id, reported_id);


--
-- Name: user_activity user_activity_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_activity
    ADD CONSTRAINT user_activity_pkey PRIMARY KEY (user_id, day);


--
-- Name: user_reports user_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reports
    ADD CONSTRAINT user_reports_pkey PRIMARY KEY (id);


--
-- Name: user_skills user_skills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT user_skills_pkey PRIMARY KEY (user_id, skill_id);


--
-- Name: auth_group_name_a6ea08ec_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_group_name_a6ea08ec_like ON public.auth_group USING btree (name varchar_pattern_ops);


--
-- Name: auth_group_permissions_group_id_b120cbf9; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_group_permissions_group_id_b120cbf9 ON public.auth_group_permissions USING btree (group_id);


--
-- Name: auth_group_permissions_permission_id_84c5c92e; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_group_permissions_permission_id_84c5c92e ON public.auth_group_permissions USING btree (permission_id);


--
-- Name: auth_permission_content_type_id_2f476e4b; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX auth_permission_content_type_id_2f476e4b ON public.auth_permission USING btree (content_type_id);


--
-- Name: django_admin_log_content_type_id_c4bce8eb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_admin_log_content_type_id_c4bce8eb ON public.django_admin_log USING btree (content_type_id);


--
-- Name: django_admin_log_user_id_c564eba6; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_admin_log_user_id_c564eba6 ON public.django_admin_log USING btree (user_id);


--
-- Name: django_session_expire_date_a5c62663; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_session_expire_date_a5c62663 ON public.django_session USING btree (expire_date);


--
-- Name: django_session_session_key_c0390e0f_like; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX django_session_session_key_c0390e0f_like ON public.django_session USING btree (session_key varchar_pattern_ops);


--
-- Name: idx_applications_contact_payment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_contact_payment_id ON public.applications USING btree (contact_payment_id);


--
-- Name: idx_applications_job_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_job_status ON public.applications USING btree (job_id, status);


--
-- Name: idx_applications_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_updated_at ON public.applications USING btree (updated_at);


--
-- Name: idx_applications_worker_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_worker_id ON public.applications USING btree (worker_id);


--
-- Name: idx_audit_log_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_action ON public.audit_log USING btree (action);


--
-- Name: idx_audit_log_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_created ON public.audit_log USING btree (created_at);


--
-- Name: idx_audit_log_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_user ON public.audit_log USING btree (user_id);


--
-- Name: idx_blacklists_blocked_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_blacklists_blocked_user_id ON public.blacklists USING btree (blocked_user_id);


--
-- Name: idx_email_log_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_log_user_id ON public.email_log USING btree (user_id);


--
-- Name: idx_invitations_employer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_employer ON public.invitations USING btree (employer_id);


--
-- Name: idx_invitations_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_job ON public.invitations USING btree (job_id);


--
-- Name: idx_invitations_worker; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitations_worker ON public.invitations USING btree (worker_id);


--
-- Name: idx_job_favorites_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_favorites_job_id ON public.job_favorites USING btree (job_id);


--
-- Name: idx_job_payments_employer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_payments_employer ON public.job_payments USING btree (employer_id);


--
-- Name: idx_job_payments_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_payments_job ON public.job_payments USING btree (job_id);


--
-- Name: idx_job_payments_paid_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_job_payments_paid_unique ON public.job_payments USING btree (job_id) WHERE ((status)::text = 'paid'::text);


--
-- Name: idx_job_photos_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_photos_job_id ON public.job_photos USING btree (job_id);


--
-- Name: idx_job_skills_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_skills_skill_id ON public.job_skills USING btree (skill_id);


--
-- Name: idx_jobs_city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_city ON public.jobs USING btree (city);


--
-- Name: idx_jobs_current_workers; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_current_workers ON public.jobs USING btree (current_workers);


--
-- Name: idx_jobs_date_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_date_time ON public.jobs USING btree (date_time);


--
-- Name: idx_jobs_employer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_employer_id ON public.jobs USING btree (employer_id);


--
-- Name: idx_jobs_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_expires ON public.jobs USING btree (expires_at) WHERE ((status)::text = 'open'::text);


--
-- Name: idx_jobs_geom; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_geom ON public.jobs USING gist (geom);


--
-- Name: idx_jobs_promoted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_promoted ON public.jobs USING btree (is_promoted, promoted_until DESC) WHERE (is_promoted = true);


--
-- Name: idx_jobs_remote_open; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_remote_open ON public.jobs USING btree (is_remote) WHERE ((status)::text = 'open'::text);


--
-- Name: idx_jobs_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_search ON public.jobs USING gin (search_vector);


--
-- Name: idx_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_status ON public.jobs USING btree (status);


--
-- Name: idx_jobs_status_and_workers; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_status_and_workers ON public.jobs USING btree (status, current_workers, max_workers);


--
-- Name: idx_jobs_status_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_jobs_status_created_at ON public.jobs USING btree (status, created_at DESC);


--
-- Name: idx_messages_application_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_application_id ON public.messages USING btree (application_id);


--
-- Name: idx_messages_client_msg_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_messages_client_msg_id ON public.messages USING btree (application_id, client_message_id) WHERE (client_message_id IS NOT NULL);


--
-- Name: idx_messages_sender_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_sender_id ON public.messages USING btree (sender_id);


--
-- Name: idx_messages_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_unread ON public.messages USING btree (application_id, sender_id) WHERE (read_at IS NULL);


--
-- Name: idx_notifications_application_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_application_id ON public.notifications USING btree (application_id);


--
-- Name: idx_notifications_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_created ON public.notifications USING btree (created_at);


--
-- Name: idx_notifications_job_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_job_id ON public.notifications USING btree (job_id);


--
-- Name: idx_notifications_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_read ON public.notifications USING btree (is_read);


--
-- Name: idx_notifications_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_user ON public.notifications USING btree (user_id);


--
-- Name: idx_outbox_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_outbox_status ON public.notification_outbox USING btree (status, created_at);


--
-- Name: idx_outbox_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_outbox_user ON public.notification_outbox USING btree (user_id, created_at);


--
-- Name: idx_profiles_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_profiles_email ON public.profiles USING btree (lower(email));


--
-- Name: idx_profiles_search; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profiles_search ON public.profiles USING gin (search_vector);


--
-- Name: idx_profiles_suspended; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profiles_suspended ON public.profiles USING btree (suspended) WHERE (suspended = true);


--
-- Name: idx_push_subscriptions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_push_subscriptions_user_id ON public.push_subscriptions USING btree (user_id);


--
-- Name: idx_ratings_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ratings_job ON public.ratings USING btree (job_id);


--
-- Name: idx_ratings_rated_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ratings_rated_user ON public.ratings USING btree (rated_user_id);


--
-- Name: idx_ratings_rater_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ratings_rater_user ON public.ratings USING btree (rater_user_id);


--
-- Name: idx_religions_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_religions_sort ON public.religions USING btree (sort_order, name);


--
-- Name: idx_skills_sort; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_skills_sort ON public.skills USING btree (sort_order, name);


--
-- Name: idx_user_reports_reported_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_reports_reported_time ON public.user_reports USING btree (reported_id, created_at DESC);


--
-- Name: idx_user_reports_reporter; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_reports_reporter ON public.user_reports USING btree (reporter_id);


--
-- Name: idx_user_reports_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_reports_status ON public.user_reports USING btree (status);


--
-- Name: idx_user_skills_skill_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_skills_skill_id ON public.user_skills USING btree (skill_id);


--
-- Name: jobs_moderation_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX jobs_moderation_status_idx ON public.jobs USING btree (moderation_status);


--
-- Name: user_activity_day_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_activity_day_idx ON public.user_activity USING btree (day);


--
-- Name: applications trg_applications_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_applications_updated_at BEFORE UPDATE ON public.applications FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: employer_subscriptions trg_employer_subscriptions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_employer_subscriptions_updated_at BEFORE UPDATE ON public.employer_subscriptions FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: jobs trg_jobs_geom; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_jobs_geom BEFORE INSERT OR UPDATE OF lat, lng ON public.jobs FOR EACH ROW EXECUTE FUNCTION public.jobs_geom_update();


--
-- Name: jobs trg_jobs_search; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_jobs_search BEFORE INSERT OR UPDATE ON public.jobs FOR EACH ROW EXECUTE FUNCTION public.jobs_search_update();


--
-- Name: jobs trg_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_jobs_updated_at BEFORE UPDATE ON public.jobs FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: profiles trg_profiles_search; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_profiles_search BEFORE INSERT OR UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.profiles_search_update();


--
-- Name: profiles trg_profiles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- Name: ratings trg_recompute_rating; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_recompute_rating AFTER INSERT OR DELETE OR UPDATE ON public.ratings FOR EACH ROW EXECUTE FUNCTION public.recompute_profile_rating();


--
-- Name: auth_group_permissions auth_group_permissio_permission_id_84c5c92e_fk_auth_perm; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissio_permission_id_84c5c92e_fk_auth_perm FOREIGN KEY (permission_id) REFERENCES public.auth_permission(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_group_permissions auth_group_permissions_group_id_b120cbf9_fk_auth_group_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_group_permissions
    ADD CONSTRAINT auth_group_permissions_group_id_b120cbf9_fk_auth_group_id FOREIGN KEY (group_id) REFERENCES public.auth_group(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: auth_permission auth_permission_content_type_id_2f476e4b_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auth_permission
    ADD CONSTRAINT auth_permission_content_type_id_2f476e4b_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: django_admin_log django_admin_log_content_type_id_c4bce8eb_fk_django_co; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_content_type_id_c4bce8eb_fk_django_co FOREIGN KEY (content_type_id) REFERENCES public.django_content_type(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: django_admin_log django_admin_log_user_id_c564eba6_fk_profiles_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.django_admin_log
    ADD CONSTRAINT django_admin_log_user_id_c564eba6_fk_profiles_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) DEFERRABLE INITIALLY DEFERRED;


--
-- Name: employer_subscriptions employer_subscriptions_employer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employer_subscriptions
    ADD CONSTRAINT employer_subscriptions_employer_id_fkey FOREIGN KEY (employer_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: applications fk_applications_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT fk_applications_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: applications fk_applications_worker_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT fk_applications_worker_id FOREIGN KEY (worker_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: blacklists fk_blacklists_blocked_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blacklists
    ADD CONSTRAINT fk_blacklists_blocked_user_id FOREIGN KEY (blocked_user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: blacklists fk_blacklists_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blacklists
    ADD CONSTRAINT fk_blacklists_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: email_log fk_email_log_notification_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_log
    ADD CONSTRAINT fk_email_log_notification_id FOREIGN KEY (notification_id) REFERENCES public.notifications(id) ON DELETE SET NULL;


--
-- Name: email_log fk_email_log_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_log
    ADD CONSTRAINT fk_email_log_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: employer_details fk_employer_details_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employer_details
    ADD CONSTRAINT fk_employer_details_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: favorites fk_favorites_target_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT fk_favorites_target_id FOREIGN KEY (target_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: favorites fk_favorites_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.favorites
    ADD CONSTRAINT fk_favorites_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: invitations fk_invitations_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitations
    ADD CONSTRAINT fk_invitations_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_favorites fk_job_favorites_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_favorites
    ADD CONSTRAINT fk_job_favorites_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_favorites fk_job_favorites_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_favorites
    ADD CONSTRAINT fk_job_favorites_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: job_payments fk_job_payments_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_payments
    ADD CONSTRAINT fk_job_payments_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_photos fk_job_photos_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_photos
    ADD CONSTRAINT fk_job_photos_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_skills fk_job_skills_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_skills
    ADD CONSTRAINT fk_job_skills_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: job_skills fk_job_skills_skill_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_skills
    ADD CONSTRAINT fk_job_skills_skill_id FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;


--
-- Name: jobs fk_jobs_employer_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT fk_jobs_employer_id FOREIGN KEY (employer_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: messages fk_messages_application_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_application_id FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE CASCADE;


--
-- Name: messages fk_messages_sender_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT fk_messages_sender_id FOREIGN KEY (sender_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: notifications fk_notifications_application_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_application_id FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE SET NULL;


--
-- Name: notifications fk_notifications_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: notifications fk_notifications_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT fk_notifications_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: profiles fk_profiles_religion_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT fk_profiles_religion_id FOREIGN KEY (religion_id) REFERENCES public.religions(id) ON DELETE SET NULL;


--
-- Name: push_subscriptions fk_push_subscriptions_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.push_subscriptions
    ADD CONSTRAINT fk_push_subscriptions_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: ratings fk_ratings_job_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT fk_ratings_job_id FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE CASCADE;


--
-- Name: ratings fk_ratings_rated_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT fk_ratings_rated_user_id FOREIGN KEY (rated_user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: ratings fk_ratings_rater_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ratings
    ADD CONSTRAINT fk_ratings_rater_user_id FOREIGN KEY (rater_user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: user_skills fk_user_skills_skill_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT fk_user_skills_skill_id FOREIGN KEY (skill_id) REFERENCES public.skills(id) ON DELETE CASCADE;


--
-- Name: user_skills fk_user_skills_user_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_skills
    ADD CONSTRAINT fk_user_skills_user_id FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: user_activity user_activity_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_activity
    ADD CONSTRAINT user_activity_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: user_reports user_reports_reported_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reports
    ADD CONSTRAINT user_reports_reported_id_fkey FOREIGN KEY (reported_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: user_reports user_reports_reporter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reports
    ADD CONSTRAINT user_reports_reporter_id_fkey FOREIGN KEY (reporter_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: user_reports user_reports_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_reports
    ADD CONSTRAINT user_reports_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: notifications Admins can delete notifications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Admins can delete notifications" ON public.notifications FOR DELETE USING ((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text));


--
-- Name: audit_log Admins can read audit_log; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Admins can read audit_log" ON public.audit_log FOR SELECT USING ((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text));


--
-- Name: ratings Anyone can read ratings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone can read ratings" ON public.ratings FOR SELECT USING (true);


--
-- Name: tariff_settings Anyone can read tariff settings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone can read tariff settings" ON public.tariff_settings FOR SELECT USING (true);


--
-- Name: messages Application participants can insert messages; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Application participants can insert messages" ON public.messages FOR INSERT WITH CHECK ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = sender_id) AND (EXISTS ( SELECT 1
   FROM public.applications a
  WHERE ((a.id = messages.application_id) AND ((a.worker_id = messages.sender_id) OR (EXISTS ( SELECT 1
           FROM public.jobs j
          WHERE ((j.id = a.job_id) AND (j.employer_id = messages.sender_id))))))))));


--
-- Name: messages Application participants can view messages; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Application participants can view messages" ON public.messages FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid IN ( SELECT applications.worker_id
   FROM public.applications
  WHERE (applications.id = messages.application_id)
UNION
 SELECT jobs.employer_id
   FROM (public.applications
     JOIN public.jobs ON ((jobs.id = applications.job_id)))
  WHERE (applications.id = messages.application_id))));


--
-- Name: jobs Employers can delete their own jobs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Employers can delete their own jobs" ON public.jobs FOR DELETE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: invitations Employers can insert invitations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Employers can insert invitations" ON public.invitations FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: jobs Employers can insert jobs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Employers can insert jobs" ON public.jobs FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: job_payments Employers can read own payments; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Employers can read own payments" ON public.job_payments FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: jobs Employers can update their own jobs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Employers can update their own jobs" ON public.jobs FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id)) WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: email_log Service can insert email logs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service can insert email logs" ON public.email_log FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'role'::text) = 'service_role'::text) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text)));


--
-- Name: notifications Service can insert notifications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service can insert notifications" ON public.notifications FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'role'::text) = 'service_role'::text) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text)));


--
-- Name: job_payments Service can insert payments; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service can insert payments" ON public.job_payments FOR INSERT WITH CHECK ((employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid));


--
-- Name: push_subscriptions Users can create own push subscriptions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can create own push subscriptions" ON public.push_subscriptions FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: applications Users can delete own applications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete own applications" ON public.applications FOR DELETE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id));


--
-- Name: push_subscriptions Users can delete own push subscriptions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete own push subscriptions" ON public.push_subscriptions FOR DELETE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: blacklists Users can delete their own blacklists; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete their own blacklists" ON public.blacklists FOR DELETE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: favorites Users can delete their own favorites; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can delete their own favorites" ON public.favorites FOR DELETE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: applications Users can insert applications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert applications" ON public.applications FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id));


--
-- Name: blacklists Users can insert blacklists; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert blacklists" ON public.blacklists FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: favorites Users can insert favorites; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert favorites" ON public.favorites FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: profiles Users can insert own profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can insert own profile" ON public.profiles FOR INSERT WITH CHECK ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = id) AND (role = ANY (ARRAY['worker'::text, 'employer'::text]))));


--
-- Name: jobs Users can read jobs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read jobs" ON public.jobs FOR SELECT USING ((((status)::text = 'open'::text) OR ((status)::text = 'completed'::text) OR ((status)::text = 'cancelled'::text)));


--
-- Name: profiles Users can read own full profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read own full profile" ON public.profiles FOR SELECT USING ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = id) OR (role = ANY (ARRAY['worker'::text, 'employer'::text]))));


--
-- Name: invitations Users can read their invitations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read their invitations" ON public.invitations FOR SELECT USING ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id) OR ((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id)));


--
-- Name: blacklists Users can read their own blacklists; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read their own blacklists" ON public.blacklists FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: favorites Users can read their own favorites; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read their own favorites" ON public.favorites FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: notifications Users can read their own notifications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can read their own notifications" ON public.notifications FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: applications Users can update own applications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own applications" ON public.applications FOR UPDATE USING ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id) OR (EXISTS ( SELECT 1
   FROM public.jobs
  WHERE ((jobs.id = applications.job_id) AND (jobs.employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid))))));


--
-- Name: job_payments Users can update own job payments; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own job payments" ON public.job_payments FOR UPDATE USING ((employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid));


--
-- Name: push_subscriptions Users can update own push subscriptions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own push subscriptions" ON public.push_subscriptions FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id)) WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: ratings Users can update own ratings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update own ratings" ON public.ratings FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = rater_user_id)) WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = rater_user_id));


--
-- Name: profiles Users can update their own profile; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can update their own profile" ON public.profiles FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = id)) WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = id));


--
-- Name: ratings Users can upsert own ratings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can upsert own ratings" ON public.ratings FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = rater_user_id));


--
-- Name: applications Users can view own applications; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can view own applications" ON public.applications FOR SELECT USING ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id) OR ((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid IN ( SELECT jobs.employer_id
   FROM public.jobs
  WHERE (jobs.id = applications.job_id)))));


--
-- Name: email_log Users can view own email logs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can view own email logs" ON public.email_log FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: push_subscriptions Users can view own push subscriptions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Users can view own push subscriptions" ON public.push_subscriptions FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: invitations Workers can update invitations; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Workers can update invitations" ON public.invitations FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id));


--
-- Name: _archive_contact_payments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public._archive_contact_payments ENABLE ROW LEVEL SECURITY;

--
-- Name: _migrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public._migrations ENABLE ROW LEVEL SECURITY;

--
-- Name: religions admin_religions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_religions ON public.religions USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'role'::text) = 'trudnikapp'::text)));


--
-- Name: skills admin_skills; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY admin_skills ON public.skills USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'role'::text) = 'trudnikapp'::text)));


--
-- Name: applications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_log audit_log_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY audit_log_select ON public.audit_log FOR SELECT TO authenticated, service_role USING ((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text));


--
-- Name: blacklists; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.blacklists ENABLE ROW LEVEL SECURITY;

--
-- Name: _archive_contact_payments contact_payments_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY contact_payments_insert ON public._archive_contact_payments FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: _archive_contact_payments contact_payments_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY contact_payments_select ON public._archive_contact_payments FOR SELECT USING ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id) OR ((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = worker_id)));


--
-- Name: _archive_contact_payments contact_payments_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY contact_payments_update ON public._archive_contact_payments FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = employer_id));


--
-- Name: email_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.email_log ENABLE ROW LEVEL SECURITY;

--
-- Name: employer_details; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employer_details ENABLE ROW LEVEL SECURITY;

--
-- Name: employer_details employer_details_insert_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY employer_details_insert_policy ON public.employer_details FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: employer_details employer_details_select_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY employer_details_select_policy ON public.employer_details FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: employer_details employer_details_update_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY employer_details_update_policy ON public.employer_details FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id)) WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: job_skills employer_job_skills; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY employer_job_skills ON public.job_skills USING ((EXISTS ( SELECT 1
   FROM public.jobs
  WHERE ((jobs.id = job_skills.job_id) AND (jobs.employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid)))));


--
-- Name: employer_subscriptions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.employer_subscriptions ENABLE ROW LEVEL SECURITY;

--
-- Name: employer_subscriptions employer_subscriptions_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY employer_subscriptions_select ON public.employer_subscriptions FOR SELECT TO authenticated, service_role USING ((employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid));


--
-- Name: favorites; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.favorites ENABLE ROW LEVEL SECURITY;

--
-- Name: invitations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.invitations ENABLE ROW LEVEL SECURITY;

--
-- Name: job_favorites; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_favorites ENABLE ROW LEVEL SECURITY;

--
-- Name: job_favorites job_favorites_delete_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY job_favorites_delete_policy ON public.job_favorites FOR DELETE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: job_favorites job_favorites_insert_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY job_favorites_insert_policy ON public.job_favorites FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: job_favorites job_favorites_select_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY job_favorites_select_policy ON public.job_favorites FOR SELECT USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: job_payments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_payments ENABLE ROW LEVEL SECURITY;

--
-- Name: job_photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_photos ENABLE ROW LEVEL SECURITY;

--
-- Name: job_photos job_photos_delete_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY job_photos_delete_policy ON public.job_photos FOR DELETE USING ((EXISTS ( SELECT 1
   FROM public.jobs
  WHERE ((jobs.id = job_photos.job_id) AND (jobs.employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid)))));


--
-- Name: job_photos job_photos_insert_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY job_photos_insert_policy ON public.job_photos FOR INSERT WITH CHECK ((EXISTS ( SELECT 1
   FROM public.jobs
  WHERE ((jobs.id = job_photos.job_id) AND (jobs.employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid)))));


--
-- Name: job_photos job_photos_select_policy; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY job_photos_select_policy ON public.job_photos FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.jobs
  WHERE ((jobs.id = job_photos.job_id) AND (jobs.employer_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid)))));


--
-- Name: job_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.job_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: messages; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

--
-- Name: _migrations migrations_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY migrations_select ON public._migrations FOR SELECT TO service_role USING (true);


--
-- Name: monetization_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.monetization_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: monetization_settings monetization_settings_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY monetization_settings_insert ON public.monetization_settings FOR INSERT WITH CHECK (((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'role'::text) = 'trudnikapp'::text)));


--
-- Name: monetization_settings monetization_settings_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY monetization_settings_select ON public.monetization_settings FOR SELECT USING (true);


--
-- Name: monetization_settings monetization_settings_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY monetization_settings_update ON public.monetization_settings FOR UPDATE USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'role'::text) = 'trudnikapp'::text)));


--
-- Name: notification_outbox; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notification_outbox ENABLE ROW LEVEL SECURITY;

--
-- Name: notifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

--
-- Name: notification_outbox outbox_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY outbox_service_all ON public.notification_outbox TO service_role USING (true) WITH CHECK (true);


--
-- Name: profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: push_subscriptions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;

--
-- Name: ratings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ratings ENABLE ROW LEVEL SECURITY;

--
-- Name: job_skills read_job_skills; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY read_job_skills ON public.job_skills FOR SELECT USING (true);


--
-- Name: religions read_religions; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY read_religions ON public.religions FOR SELECT USING (true);


--
-- Name: skills read_skills; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY read_skills ON public.skills FOR SELECT USING (true);


--
-- Name: user_skills read_user_skills; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY read_user_skills ON public.user_skills FOR SELECT USING (true);


--
-- Name: receipts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.receipts ENABLE ROW LEVEL SECURITY;

--
-- Name: receipts receipts_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY receipts_insert ON public.receipts FOR INSERT WITH CHECK ((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text));


--
-- Name: receipts receipts_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY receipts_select ON public.receipts FOR SELECT USING ((((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid IN ( SELECT _archive_contact_payments.employer_id
   FROM public._archive_contact_payments
  WHERE (_archive_contact_payments.id = receipts.contact_payment_id)
UNION
 SELECT _archive_contact_payments.worker_id
   FROM public._archive_contact_payments
  WHERE (_archive_contact_payments.id = receipts.contact_payment_id))) OR (((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text)));


--
-- Name: receipts receipts_update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY receipts_update ON public.receipts FOR UPDATE USING ((((current_setting('request.jwt.claims'::text, true))::json ->> 'app_role'::text) = 'admin'::text));


--
-- Name: religions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.religions ENABLE ROW LEVEL SECURITY;

--
-- Name: schema_migrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

--
-- Name: schema_migrations schema_migrations_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY schema_migrations_select ON public.schema_migrations FOR SELECT TO service_role USING (true);


--
-- Name: site_pages; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.site_pages ENABLE ROW LEVEL SECURITY;

--
-- Name: site_pages site_pages_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY site_pages_read ON public.site_pages FOR SELECT TO anon, authenticated USING (true);


--
-- Name: site_pages site_pages_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY site_pages_write ON public.site_pages TO service_role USING (true) WITH CHECK (true);


--
-- Name: skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.skills ENABLE ROW LEVEL SECURITY;

--
-- Name: tariff_settings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.tariff_settings ENABLE ROW LEVEL SECURITY;

--
-- Name: user_skills user_own_skills; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY user_own_skills ON public.user_skills USING (((((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid = user_id));


--
-- Name: user_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: user_reports user_reports_self_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY user_reports_self_insert ON public.user_reports FOR INSERT WITH CHECK ((reporter_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid));


--
-- Name: user_reports user_reports_self_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY user_reports_self_select ON public.user_reports FOR SELECT USING ((reporter_id = (((current_setting('request.jwt.claims'::text, true))::json ->> 'user_id'::text))::uuid));


--
-- Name: user_skills; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_skills ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

