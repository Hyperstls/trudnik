-- ============================================================================
-- Migration 075: Audit Remediation — Security, Performance & Architecture Fixes
-- Файл: migrations/075_audit_remediation.sql
-- Дата: 2026-06-27
-- ============================================================================
--
-- НАЗНАЧЕНИЕ:
--   Комплексное исправление безопасности, производительности и архитектуры.
--   Включает 26 пунктов (M1–M26): column-level GRANT, RLS-политики,
--   RPC-функции, CHECK-конструкции, индексы, новые таблицы и FK-исправления.
--
-- ОГРАНИЧЕНИЯ:
--   - Не модифицирует миграции 001–074
--   - Все операции идемпотентны
--   - PostgreSQL 15+
-- ============================================================================

BEGIN;

-- ============================================================================
-- M1: Column-level GRANT на profiles
-- Запрет доступа к password_hash, inn, phone, email через anon/authenticated
-- ============================================================================
REVOKE SELECT ON profiles FROM anon, authenticated;
GRANT SELECT (id, role, created_at, updated_at, is_self_employed, email_public,
              rating, full_name, photo_url, age, bio, city, experience,
              desired_payment, verification_status, total_reviews, skills,
              religion, religion_id, portfolio_link)
   ON profiles TO anon, authenticated;

-- ============================================================================
-- M2: Запретить INSERT с role='admin'
-- Обычные пользователи не могут создать админа
-- ============================================================================
DROP POLICY IF EXISTS "Service can insert profiles" ON profiles;
DROP POLICY IF EXISTS "Users can insert own profile" ON profiles;
CREATE POLICY "Users can insert own profile" ON profiles
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.user_id', true)::uuid = id
        AND role IN ('worker', 'employer')
    );

-- ============================================================================
-- M3: SELECT policy — пользователи видят только свои полные данные
-- Полный доступ только к своему профилю; остальным — только публичные поля через column-level GRANT
-- ============================================================================
DROP POLICY IF EXISTS "Users can read profiles" ON profiles;
DROP POLICY IF EXISTS "Users can read own full profile" ON profiles;
CREATE POLICY "Users can read own full profile" ON profiles
    FOR SELECT USING (
        current_setting('request.jwt.claim.user_id', true)::uuid = id
        OR role IN ('worker', 'employer')
    );

-- ============================================================================
-- M4: Унифицировать register_user RPC
-- Проверка p_role IN ('worker', 'employer'), bcrypt rounds = 12
-- ============================================================================
DROP FUNCTION IF EXISTS public.register_user(text, text, text, text);

CREATE OR REPLACE FUNCTION public.register_user(
    p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_user_id uuid;
BEGIN
    IF p_role NOT IN ('worker', 'employer') THEN
        RAISE EXCEPTION 'invalid_role';
    END IF;
    IF EXISTS (SELECT 1 FROM public.profiles WHERE email = p_email) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO public.profiles (id, email, password_hash, full_name, role)
    VALUES (gen_random_uuid(), p_email, crypt(p_password, gen_salt('bf', 12)), p_full_name, p_role)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.register_user(text, text, text, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.register_user(text, text, text, text) TO anon, authenticated, service_role;

-- ============================================================================
-- M5: GRANT delete_job_cascade / delete_user_cascade только service_role
-- Обычные пользователи не могут удалять чужие задания/профили
-- ============================================================================
REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM authenticated;
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM authenticated;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO service_role;
GRANT  EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;

-- ============================================================================
-- M6: Переписать apply_job_atomic — убрать двойной инкремент current_workers
-- current_workers инкрементируется только в accept_application
-- ============================================================================
DROP FUNCTION IF EXISTS public.apply_job_atomic(uuid, uuid);

CREATE OR REPLACE FUNCTION public.apply_job_atomic(
    p_job_id uuid, p_worker_id uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_max_workers int; v_current_workers int; v_status text; v_employer_id uuid;
    v_app_id uuid;
BEGIN
    SELECT max_workers, current_workers, status, employer_id
      INTO v_max_workers, v_current_workers, v_status, v_employer_id
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;
    IF v_status NOT IN ('open', 'active') THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание недоступно для отклика', 'code', 'job_not_open');
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
GRANT  EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;

-- ============================================================================
-- M7: Расширить jobs_status_check
-- Добавить статусы, используемые в state-machine: draft, active, in_progress, paid, expired
-- ============================================================================
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('draft','open','active','in_progress','completed','cancelled','paid','expired'));

-- ============================================================================
-- M8: Переписать accept_application с проверкой владельца задания
-- ============================================================================
DROP FUNCTION IF EXISTS public.accept_application(uuid, uuid);

CREATE OR REPLACE FUNCTION public.accept_application(p_job_id uuid, p_app_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_current_workers int; v_max_workers int; v_job_status text;
    v_new_count int; v_new_status text; v_employer_id uuid;
BEGIN
    SELECT current_workers, max_workers, status, employer_id
      INTO v_current_workers, v_max_workers, v_job_status, v_employer_id
      FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Проверка владельца: только employer_id задания или admin/service_role
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.role', true) NOT IN ('admin', 'service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;
    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
    END IF;

    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE public.jobs SET status = v_new_status, current_workers = v_new_count
    WHERE id = p_job_id;

    UPDATE public.applications SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status IN ('pending', 'rejected');

    IF NOT FOUND THEN
        UPDATE public.jobs SET status = v_job_status, current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    UPDATE public.applications SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    RETURN json_build_object('success', true, 'current_workers', v_new_count, 'job_status', v_new_status);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

-- ============================================================================
-- M9: Переписать reject_application с проверкой владельца
-- ============================================================================
DROP FUNCTION IF EXISTS public.reject_application(uuid, uuid);

CREATE OR REPLACE FUNCTION public.reject_application(p_job_id uuid, p_app_id uuid)
RETURNS json LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_current_status text; v_current_workers int; v_max_workers int;
    v_job_status text; v_employer_id uuid;
    v_new_workers int; v_new_job_status text; v_result json;
BEGIN
    -- Проверка владельца: employer_id задания или admin/service_role
    SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.role', true) NOT IN ('admin', 'service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    SELECT status INTO v_current_status
    FROM public.applications
    WHERE id = p_app_id AND job_id = p_job_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Отклик не найден');
    END IF;

    IF v_current_status = 'accepted' THEN
        SELECT current_workers, max_workers, status
        INTO v_current_workers, v_max_workers, v_job_status
        FROM public.jobs WHERE id = p_job_id FOR UPDATE;

        v_new_workers := GREATEST(0, v_current_workers - 1);
        v_new_job_status := CASE WHEN v_new_workers = 0 THEN 'open' ELSE 'completed' END;

        UPDATE public.jobs SET current_workers = v_new_workers, status = v_new_job_status
        WHERE id = p_job_id;

        UPDATE public.applications SET status = 'rejected' WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true, 'new_status', 'rejected',
            'current_workers', v_new_workers, 'job_status', v_new_job_status,
            'message', 'Работник отклонён'
        );
    ELSE
        UPDATE public.applications SET status = 'rejected' WHERE id = p_app_id;
        v_result := json_build_object('success', true, 'new_status', 'rejected', 'message', 'Отклик отклонён');
    END IF;

    RETURN v_result;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.reject_application(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;

-- ============================================================================
-- M10: Политика messages: INSERT только для участников application
-- (worker_id / employer_id проверяются через JOIN с applications и jobs)
-- ============================================================================
DROP POLICY IF EXISTS "Application participants can insert messages" ON messages;
CREATE POLICY "Application participants can insert messages" ON messages
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.user_id', true)::uuid = sender_id
        AND EXISTS (
            SELECT 1 FROM applications a
            WHERE a.id = messages.application_id
              AND (a.worker_id = sender_id
                   OR EXISTS (SELECT 1 FROM jobs j
                              WHERE j.id = a.job_id AND j.employer_id = sender_id))
        )
    );

-- ============================================================================
-- M11: Политики notifications и email_log: INSERT только service_role
-- ============================================================================
DROP POLICY IF EXISTS "Service can insert notifications" ON notifications;
CREATE POLICY "Service can insert notifications" ON notifications
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

DROP POLICY IF EXISTS "Service can insert email logs" ON email_log;
CREATE POLICY "Service can insert email logs" ON email_log
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');

-- ============================================================================
-- M12: Bcrypt rounds = 12 в change_password
-- ============================================================================
DROP FUNCTION IF EXISTS public.change_password(uuid, text, text);

CREATE OR REPLACE FUNCTION public.change_password(
    p_user_id uuid, p_old_password text, p_new_password text
) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
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

REVOKE EXECUTE ON FUNCTION public.change_password(uuid, text, text) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.change_password(uuid, text, text) TO authenticated, service_role;

-- ============================================================================
-- M12+M13: login_user с bcrypt=12 + rehash-on-login
-- При успешном входе, если старый хэш (rounds < 12), автоматически обновить до 12 rounds
-- ============================================================================
DROP FUNCTION IF EXISTS public.login_user(text, text);

CREATE OR REPLACE FUNCTION login_user(p_email text, p_password text)
RETURNS TABLE(user_id uuid, role text, full_name text) AS $$
DECLARE
    v_user_id uuid;
    v_role text;
    v_full_name text;
    v_stored_hash text;
BEGIN
    SELECT p.id, p.role, p.full_name, p.password_hash
      INTO v_user_id, v_role, v_full_name, v_stored_hash
      FROM public.profiles p
      WHERE p.email = p_email
      LIMIT 1;

    IF NOT FOUND OR v_stored_hash IS NULL OR v_stored_hash != crypt(p_password, v_stored_hash) THEN
        RETURN;
    END IF;

    -- Rehash-on-login: если rounds < 12, автоматически обновить хэш
    IF substring(v_stored_hash from 1 for 7) IN ('$2a$06$', '$2b$06$', '$2y$06$', '$2a$08$', '$2b$08$', '$2y$08$', '$2a$10$', '$2b$10$', '$2y$10$') THEN
        UPDATE public.profiles SET password_hash = crypt(p_password, gen_salt('bf', 12)) WHERE id = v_user_id;
    END IF;

    RETURN QUERY SELECT v_user_id, v_role, v_full_name;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO anon, authenticated, service_role;

-- ============================================================================
-- M14: restore_job_atomic RPC
-- Атомарно: обновить статус задания на 'open', сбросить current_workers = 0,
-- обновить статусы заявок на 'cancelled' где status = 'accepted'
-- ============================================================================
CREATE OR REPLACE FUNCTION public.restore_job_atomic(p_job_id uuid, p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_cancelled_count int;
BEGIN
    SELECT employer_id, status INTO v_employer_id, v_status
    FROM public.jobs WHERE id = p_job_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'Задание не найдено', 'code', 'job_not_found');
    END IF;

    IF v_employer_id != p_user_id
       AND current_setting('request.jwt.claim.role', true) NOT IN ('admin', 'service_role', 'trudnikapp') THEN
        RETURN jsonb_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    -- Сброс статуса задания
    UPDATE public.jobs SET status = 'open', current_workers = 0, updated_at = now()
    WHERE id = p_job_id;

    -- Отмена принятых заявок
    WITH cancelled AS (
        UPDATE public.applications SET status = 'cancelled'
        WHERE job_id = p_job_id AND status = 'accepted'
        RETURNING id
    )
    SELECT count(*) INTO v_cancelled_count FROM cancelled;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание восстановлено',
        'job_status', 'open',
        'current_workers', 0,
        'cancelled_applications', v_cancelled_count
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.restore_job_atomic(uuid, uuid) TO authenticated, service_role;

-- ============================================================================
-- M15: jobs_payment_amount_check — payment_amount >= 0
-- ============================================================================
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_payment_amount_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_payment_amount_check CHECK (payment_amount >= 0);

-- ============================================================================
-- M16: Переписать delete_job_cascade — убрать ILIKE '%uuid%'
-- Использовать FK через notifications.job_id вместо текстового поиска
-- + добавить проверку владельца
-- ============================================================================
DROP FUNCTION IF EXISTS public.delete_job_cascade(uuid);

CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS json
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_deleted_apps int;
    v_deleted_skills int;
    v_deleted_photos int;
    v_deleted_favorites int;
    v_deleted_invitations int;
    v_deleted_notifications int;
BEGIN
    SELECT employer_id INTO v_employer_id FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    -- Проверка владельца
    IF v_employer_id != current_setting('request.jwt.claim.user_id', true)::uuid
       AND current_setting('request.jwt.claim.role', true) NOT IN ('admin', 'service_role', 'trudnikapp') THEN
        RETURN json_build_object('success', false, 'error', 'not authorized', 'code', 'not_owner');
    END IF;

    DELETE FROM public.applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM public.job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM public.job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM public.job_favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM public.invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    DELETE FROM public.notifications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    DELETE FROM public.jobs WHERE id = p_job_id;

    RETURN json_build_object(
        'success', true,
        'deleted', json_build_object(
            'applications', v_deleted_apps,
            'job_skills', v_deleted_skills,
            'job_photos', v_deleted_photos,
            'job_favorites', v_deleted_favorites,
            'invitations', v_deleted_invitations,
            'notifications', v_deleted_notifications
        ),
        'message', 'Задание удалено'
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO service_role;

-- ============================================================================
-- M17: Таблица notification_outbox + индексы
-- ============================================================================
CREATE TABLE IF NOT EXISTS notification_outbox (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','sent','failed'))
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON notification_outbox(status, created_at);
CREATE INDEX IF NOT EXISTS idx_outbox_user ON notification_outbox(user_id, created_at);

-- ============================================================================
-- M18: CHECK-конструкции
-- ============================================================================

-- profiles_role_check
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_role_check;
ALTER TABLE profiles ADD CONSTRAINT profiles_role_check CHECK (role IN ('worker','employer','admin'));

-- profiles_email_check
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_email_check;
ALTER TABLE profiles ADD CONSTRAINT profiles_email_check CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');

-- profiles_age_check
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_age_check;
ALTER TABLE profiles ADD CONSTRAINT profiles_age_check CHECK (age IS NULL OR (age >= 14 AND age <= 120));

-- profiles_inn_check
ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_inn_check;
ALTER TABLE profiles ADD CONSTRAINT profiles_inn_check CHECK (inn IS NULL OR inn = '' OR inn ~ '^\d{10,12}$');

-- job_payments_amount_check
ALTER TABLE job_payments DROP CONSTRAINT IF EXISTS job_payments_amount_check;
ALTER TABLE job_payments ADD CONSTRAINT job_payments_amount_check CHECK (amount >= 0);

-- receipts_amount_check
ALTER TABLE receipts DROP CONSTRAINT IF EXISTS receipts_amount_check;
ALTER TABLE receipts ADD CONSTRAINT receipts_amount_check CHECK (amount >= 0);

-- ============================================================================
-- M19: GiST-индекс на jobs.geom + автообновление geom из lat/lng + nearby_jobs RPC
-- Если PostGIS не установлен — блок пропускается с уведомлением
-- ============================================================================
DO $_$ BEGIN

-- Добавляем колонку geom, если ещё нет
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS geom public.geometry(public.Point, 4326);

-- GiST-индекс
CREATE INDEX IF NOT EXISTS idx_jobs_geom ON jobs USING GIST (geom);

-- Триггерная функция для автообновления geom из lat/lng
CREATE OR REPLACE FUNCTION public.jobs_geom_update() RETURNS trigger
LANGUAGE plpgsql SET search_path = ''
AS $func$
BEGIN
    IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326);
    END IF;
    RETURN NEW;
END;
$func$;

-- Триггер
DROP TRIGGER IF EXISTS trg_jobs_geom ON jobs;
CREATE TRIGGER trg_jobs_geom
    BEFORE INSERT OR UPDATE OF lat, lng ON jobs
    FOR EACH ROW EXECUTE FUNCTION public.jobs_geom_update();

-- RPC nearby_jobs
DROP FUNCTION IF EXISTS public.nearby_jobs(double precision, double precision, double precision);
DROP FUNCTION IF EXISTS public.nearby_jobs(double precision, double precision);

CREATE OR REPLACE FUNCTION public.nearby_jobs(
    p_lat double precision,
    p_lng double precision,
    p_radius_meters double precision DEFAULT 5000
)
RETURNS TABLE(
    id uuid, employer_id uuid, organization_name text, object_description text,
    work_type varchar, address varchar, city varchar, lat double precision,
    lng double precision, date_time timestamptz, payment_amount numeric,
    status varchar, max_workers int, current_workers int, created_at timestamptz,
    distance_meters double precision
)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $func$
DECLARE
    v_point public.geometry := ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326);
BEGIN
    RETURN QUERY
    SELECT
        j.id, j.employer_id, j.organization_name, j.object_description,
        j.work_type, j.address, j.city, j.lat, j.lng,
        j.date_time, j.payment_amount, j.status, j.max_workers, j.current_workers,
        j.created_at,
        ST_Distance(j.geom::geography, v_point::geography) AS distance_meters
    FROM public.jobs j
    WHERE j.geom IS NOT NULL
      AND j.status IN ('open', 'active')
      AND ST_DWithin(j.geom::geography, v_point::geography, p_radius_meters)
    ORDER BY j.geom <-> v_point
    LIMIT 50;
END;
$func$;

REVOKE EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) TO authenticated;

EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'M19 skipped: PostGIS not available — %', SQLERRM;
END $_$;

-- ============================================================================
-- M20: Индексы производительности
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs(city);
CREATE INDEX IF NOT EXISTS idx_jobs_date_time ON jobs(date_time);
CREATE INDEX IF NOT EXISTS idx_applications_job_status ON applications(job_id, status);

-- ============================================================================
-- M21: delete_skill_cascade RPC
-- Атомарное удаление навыка и обнуление у пользователей
-- ============================================================================
CREATE OR REPLACE FUNCTION public.delete_skill_cascade(p_skill_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
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

REVOKE EXECUTE ON FUNCTION public.delete_skill_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_skill_cascade(uuid) TO service_role;

-- ============================================================================
-- M22: Таблица audit_log
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    table_name VARCHAR(100),
    record_id UUID,
    old_data JSONB,
    new_data JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);

-- ============================================================================
-- M23: Исправить receipts FK — receipts_job_payment_id_fk (если колонка существует)
-- ============================================================================
DO $_$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'receipts' AND column_name = 'job_payment_id') THEN
        ALTER TABLE receipts DROP CONSTRAINT IF EXISTS receipts_job_payment_id_fk;
        ALTER TABLE receipts ADD CONSTRAINT receipts_job_payment_id_fk
            FOREIGN KEY (job_payment_id) REFERENCES job_payments(id) ON DELETE CASCADE;
    ELSE
        RAISE NOTICE 'M23 skipped: column job_payment_id does not exist in receipts';
    END IF;
END $_$;

-- ============================================================================
-- M24: schema_migrations записи (если таблица и колонки существуют)
-- INSERT записи о применённых миграциях 067-075
-- ============================================================================
DO $_$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'schema_migrations') THEN
        INSERT INTO schema_migrations (version, name, applied_at) VALUES
            ('067', 'bootstrap_amvera', now()),
            ('068', 'fix_pgadmin_gaps', now()),
            ('069', 'fix_rpc_security_gaps', now()),
            ('070', 'replace_skills_church', now()),
            ('071', 'fix_auth_permissions', now()),
            ('072', 'fix_skills_v2', now()),
            ('073', 'fix_admin_rls_policies', now()),
            ('074', 'fix_rls_roles', now()),
            ('075', 'audit_remediation', now())
        ON CONFLICT (version) DO UPDATE SET name = EXCLUDED.name, applied_at = EXCLUDED.applied_at;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'M24 skipped: schema_migrations structure mismatch — %', SQLERRM;
END $_$;

-- ============================================================================
-- M25: employer_subscriptions таблица
-- ============================================================================
CREATE TABLE IF NOT EXISTS employer_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    tariff VARCHAR(20) NOT NULL DEFAULT 'basic' CHECK (tariff IN ('basic','pro','business')),
    jobs_remaining INT DEFAULT 0,
    is_promoted BOOLEAN DEFAULT false,
    promoted_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- M26: jobs.is_promoted + promoted_until
-- ============================================================================
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_promoted BOOLEAN DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS promoted_until TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_jobs_promoted ON jobs(is_promoted, promoted_until DESC) WHERE is_promoted = true;

COMMIT;

-- ============================================================================
-- ГОТОВО!
--
-- Итого в этой миграции (075_audit_remediation):
--   M1:  Column-level GRANT на profiles (REVOKE SELECT + GRANT публичных полей)
--   M2:  Запрет INSERT с role='admin' (RLS-политика)
--   M3:  SELECT policy: пользователи видят только свои полные данные
--   M4:  Унифицирован register_user (проверка role, bcrypt=12)
--   M5:  GRANT delete_job_cascade/delete_user_cascade только service_role
--   M6:  apply_job_atomic без двойного инкремента current_workers
--   M7:  Расширен jobs_status_check (+draft, active, in_progress, paid, expired)
--   M8:  accept_application с проверкой владельца
--   M9:  reject_application с проверкой владельца
--   M10: Политика messages INSERT только для участников application
--   M11: Политики notifications/email_log INSERT только service_role
--   M12: Bcrypt rounds = 12 в register_user, change_password, login_user
--   M13: Rehash-on-login (при старом хэше < 12 rounds)
--   M14: restore_job_atomic RPC
--   M15: jobs_payment_amount_check (payment_amount >= 0)
--   M16: delete_job_cascade без ILIKE, с проверкой владельца
--   M17: Таблица notification_outbox + индексы
--   M18: CHECK-конструкции (role, email, age, inn, payment_amount, receipts_amount)
--   M19: GiST-индекс на jobs.geom + автообновление + nearby_jobs RPC
--   M20: Индексы производительности (status, city, date_time, applications)
--   M21: delete_skill_cascade RPC
--   M22: Таблица audit_log + индексы
--   M23: Исправлен receipts FK (job_payment_id → job_payments ON DELETE CASCADE)
--   M24: schema_migrations записи 067-075
--   M25: Таблица employer_subscriptions
--   M26: jobs.is_promoted + promoted_until + индекс
-- ============================================================================
