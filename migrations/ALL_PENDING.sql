-- ============================================================
-- ALL_PENDING_MIGRATIONS.sql
-- Единый скрипт для применения миграций 039-042
-- Выполнить в Supabase SQL Editor (https://supabase.com/dashboard/project/***REMOVED***/sql)
-- ============================================================

-- ═══════════════════════════════════════════════════════════════
-- ШАГ 0: Исправляем exec_sql для поддержки DDL
-- Текущая версия оборачивает SQL в SELECT ... FROM (...) t,
-- что не позволяет выполнять CREATE/ALTER/DROP.
-- ═══════════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION public.exec_sql(sql_query text)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    result JSONB;
    requesting_user_id uuid;
    trimmed text;
BEGIN
    IF current_setting('role', true) != 'service_role' THEN
        RAISE EXCEPTION 'Только service_role может выполнять SQL-запросы через exec_sql';
    END IF;

    trimmed := trim(sql_query);
    IF lower(substring(trimmed, 1, 6)) = 'select' 
       OR lower(substring(trimmed, 1, 4)) = 'with' THEN
        EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;
        RETURN coalesce(result, '[]'::jsonb);
    ELSE
        EXECUTE sql_query;
        RETURN '[]'::jsonb;
    END IF;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;


-- ═══════════════════════════════════════════════════════════════
-- МИГРАЦИЯ 039: Atomic RPC-процедуры
-- ═══════════════════════════════════════════════════════════════

-- 1. accept_application
CREATE OR REPLACE FUNCTION accept_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_count int;
    v_new_status text;
    v_result json;
BEGIN
    SELECT current_workers, max_workers, status
    INTO v_current_workers, v_max_workers, v_job_status
    FROM jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;

    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
    END IF;

    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE jobs
    SET status = v_new_status,
        current_workers = v_new_count
    WHERE id = p_job_id;

    UPDATE applications
    SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status = 'pending';

    IF NOT FOUND THEN
        UPDATE jobs
        SET status = v_job_status,
            current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    UPDATE applications
    SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    v_result := json_build_object(
        'success', true,
        'new_status', 'accepted',
        'current_workers', v_new_count,
        'job_status', v_new_status,
        'message', 'Работник принят'
    );

    RETURN v_result;
END;
$$;


-- 2. reject_application
CREATE OR REPLACE FUNCTION reject_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_status text;
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_workers int;
    v_new_job_status text;
    v_result json;
BEGIN
    SELECT status INTO v_current_status
    FROM applications
    WHERE id = p_app_id AND job_id = p_job_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Отклик не найден');
    END IF;

    IF v_current_status = 'accepted' THEN
        SELECT current_workers, max_workers, status
        INTO v_current_workers, v_max_workers, v_job_status
        FROM jobs
        WHERE id = p_job_id
        FOR UPDATE;

        v_new_workers := GREATEST(0, v_current_workers - 1);
        v_new_job_status := CASE WHEN v_new_workers = 0 THEN 'open' ELSE 'completed' END;

        UPDATE jobs
        SET current_workers = v_new_workers,
            status = v_new_job_status
        WHERE id = p_job_id;

        UPDATE applications
        SET status = 'rejected'
        WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true,
            'new_status', 'rejected',
            'current_workers', v_new_workers,
            'job_status', v_new_job_status,
            'message', 'Работник отклонён'
        );
    ELSE
        UPDATE applications
        SET status = 'rejected'
        WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true,
            'new_status', 'rejected',
            'message', 'Отклик отклонён'
        );
    END IF;

    RETURN v_result;
END;
$$;


-- 3. delete_job_cascade
CREATE OR REPLACE FUNCTION delete_job_cascade(
    p_job_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_deleted_apps int;
    v_deleted_skills int;
    v_deleted_photos int;
    v_deleted_favorites int;
    v_deleted_invitations int;
    v_deleted_notifications int;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM jobs WHERE id = p_job_id) THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    DELETE FROM applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM job_favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    DELETE FROM notifications WHERE message ILIKE '%' || p_job_id::text || '%';
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    DELETE FROM jobs WHERE id = p_job_id;

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


-- 4. delete_user_cascade
CREATE OR REPLACE FUNCTION delete_user_cascade(
    p_user_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_role text;
    v_deleted json;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Пользователь не найден');
    END IF;

    IF v_role = 'employer' THEN
        PERFORM delete_job_cascade(job.id)
        FROM (SELECT id FROM jobs WHERE employer_id = p_user_id) AS job;
    END IF;

    DELETE FROM applications WHERE worker_id = p_user_id;
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE target_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE blocked_user_id = p_user_id;
    DELETE FROM ratings WHERE rater_user_id = p_user_id;
    DELETE FROM ratings WHERE rated_user_id = p_user_id;
    DELETE FROM invitations WHERE employer_id = p_user_id;
    DELETE FROM invitations WHERE worker_id = p_user_id;
    DELETE FROM user_skills WHERE user_id = p_user_id;
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;
    DELETE FROM messages WHERE sender_id = p_user_id;

    DELETE FROM profiles WHERE id = p_user_id;

    RETURN json_build_object(
        'success', true,
        'message', 'Пользователь удалён'
    );
END;
$$;


-- ═══════════════════════════════════════════════════════════════
-- МИГРАЦИЯ 040: Schema Versioning
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ DEFAULT NOW(),
    description TEXT
);

ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Admin can read schema_migrations" ON public.schema_migrations;
    CREATE POLICY "Admin can read schema_migrations" ON public.schema_migrations
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM profiles
                WHERE profiles.id = (SELECT auth.uid())
                  AND profiles.role = 'admin'
            )
        );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'schema_migrations policy: %', SQLERRM;
END $$;

INSERT INTO public.schema_migrations (version, description)
VALUES ('039', 'Atomic RPC: accept_application, reject_application, delete_job_cascade, delete_user_cascade'),
       ('040', 'Schema versioning: таблица schema_migrations с RLS')
ON CONFLICT (version) DO NOTHING;


-- ═══════════════════════════════════════════════════════════════
-- МИГРАЦИЯ 041: FK для messages
-- ═══════════════════════════════════════════════════════════════

-- 1. FK: messages.sender_id → profiles.id ON DELETE CASCADE
DO $$
DECLARE
    fk_exists boolean;
    current_rule text;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = 'messages'
          AND ccu.table_name = 'profiles'
          AND ccu.column_name = 'id'
    ) INTO fk_exists;

    IF fk_exists THEN
        -- Проверяем, CASCADE ли уже
        SELECT rc.delete_rule INTO current_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
        WHERE tc.table_name = 'messages'
          AND tc.constraint_name = 'messages_sender_id_fkey';

        IF current_rule != 'CASCADE' THEN
            -- Удаляем старый FK и создаём новый с CASCADE
            ALTER TABLE public.messages DROP CONSTRAINT messages_sender_id_fkey;
            DELETE FROM messages WHERE sender_id IS NOT NULL AND sender_id NOT IN (SELECT id FROM profiles);
            ALTER TABLE public.messages
                ADD CONSTRAINT messages_sender_id_fkey
                FOREIGN KEY (sender_id) REFERENCES public.profiles(id) ON DELETE CASCADE;
            RAISE NOTICE 'FK messages.sender_id → profiles.id updated to ON DELETE CASCADE';
        ELSE
            RAISE NOTICE 'FK messages.sender_id → profiles.id already ON DELETE CASCADE';
        END IF;
    ELSE
        DELETE FROM messages WHERE sender_id IS NOT NULL AND sender_id NOT IN (SELECT id FROM profiles);
        ALTER TABLE public.messages
            ADD CONSTRAINT messages_sender_id_fkey
            FOREIGN KEY (sender_id) REFERENCES public.profiles(id) ON DELETE CASCADE;
        RAISE NOTICE 'FK messages.sender_id → profiles.id created with ON DELETE CASCADE';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'FK messages.sender_id: %', SQLERRM;
END $$;

-- 2. FK: messages.application_id → applications.id ON DELETE CASCADE
DO $$
DECLARE
    fk_exists boolean;
    col_exists boolean;
    current_rule text;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'application_id'
    ) INTO col_exists;

    IF col_exists THEN
        SELECT EXISTS (
            SELECT 1 FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = 'messages'
              AND ccu.table_name = 'applications'
              AND ccu.column_name = 'id'
        ) INTO fk_exists;

        IF fk_exists THEN
            SELECT rc.delete_rule INTO current_rule
            FROM information_schema.table_constraints tc
            JOIN information_schema.referential_constraints rc
                ON tc.constraint_name = rc.constraint_name
            WHERE tc.table_name = 'messages'
              AND tc.constraint_name = 'messages_application_id_fkey';

            IF current_rule != 'CASCADE' THEN
                ALTER TABLE public.messages DROP CONSTRAINT messages_application_id_fkey;
                DELETE FROM messages WHERE application_id IS NOT NULL AND application_id NOT IN (SELECT id FROM applications);
                ALTER TABLE public.messages
                    ADD CONSTRAINT messages_application_id_fkey
                    FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE CASCADE;
                RAISE NOTICE 'FK messages.application_id updated to ON DELETE CASCADE';
            ELSE
                RAISE NOTICE 'FK messages.application_id already ON DELETE CASCADE';
            END IF;
        ELSE
            DELETE FROM messages WHERE application_id IS NOT NULL AND application_id NOT IN (SELECT id FROM applications);
            ALTER TABLE public.messages
                ADD CONSTRAINT messages_application_id_fkey
                FOREIGN KEY (application_id) REFERENCES public.applications(id) ON DELETE CASCADE;
            RAISE NOTICE 'FK messages.application_id created with ON DELETE CASCADE';
        END IF;
    ELSE
        RAISE NOTICE 'Column messages.application_id does not exist — skipped';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'FK messages.application_id: %', SQLERRM;
END $$;

INSERT INTO public.schema_migrations (version, description)
VALUES ('041', 'FK messages: sender_id → profiles.id, application_id → applications.id ON DELETE CASCADE')
ON CONFLICT (version) DO NOTHING;


-- ═══════════════════════════════════════════════════════════════
-- МИГРАЦИЯ 042: Чистка дубликатов и мёртвых таблиц
-- ═══════════════════════════════════════════════════════════════

-- 1. Дубликаты колонок: notifications.read vs is_read
DO $$
DECLARE
    has_read boolean;
    has_is_read boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notifications' AND column_name = 'read'
    ) INTO has_read;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notifications' AND column_name = 'is_read'
    ) INTO has_is_read;

    IF has_read AND has_is_read THEN
        UPDATE notifications SET is_read = read::boolean WHERE is_read IS NULL AND read IS NOT NULL;
        ALTER TABLE public.notifications DROP COLUMN IF EXISTS read;
        RAISE NOTICE 'notifications: колонка read удалена (оставлена is_read)';
    ELSIF has_read AND NOT has_is_read THEN
        ALTER TABLE public.notifications RENAME COLUMN read TO is_read;
        RAISE NOTICE 'notifications: колонка read переименована в is_read';
    ELSE
        RAISE NOTICE 'notifications: дубликатов нет (только is_read)';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'notifications cleanup: %', SQLERRM;
END $$;

-- 2. Дубликаты колонок: profiles.religion vs religion_id
DO $$
DECLARE
    has_religion_text boolean;
    has_religion_id boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'profiles' AND column_name = 'religion'
    ) INTO has_religion_text;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'profiles' AND column_name = 'religion_id'
    ) INTO has_religion_id;

    IF has_religion_text AND has_religion_id THEN
        COMMENT ON COLUMN public.profiles.religion IS 'DEPRECATED: используйте religion_id (UUID → religions.id)';
        RAISE NOTICE 'profiles: обе колонки. religion помечена как DEPRECATED.';
    ELSIF has_religion_text THEN
        RAISE NOTICE 'profiles: только religion (TEXT). Рекомендуется миграция на religion_id (UUID).';
    ELSE
        RAISE NOTICE 'profiles: дубликатов нет';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'profiles cleanup: %', SQLERRM;
END $$;

-- 3. Пометка мёртвых таблиц как DEPRECATED
DO $$ BEGIN
    COMMENT ON TABLE public.spatial_ref_sys IS 'DEPRECATED: системная таблица PostGIS, не используется приложением.';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

INSERT INTO public.schema_migrations (version, description)
VALUES ('042', 'Cleanup: дубликаты колонок, пометка мёртвых таблиц')
ON CONFLICT (version) DO NOTHING;
