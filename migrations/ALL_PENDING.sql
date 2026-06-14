-- ============================================================
-- ВСЕ ОСТАВШИЕСЯ МИГРАЦИИ В ОДНОМ ФАЙЛЕ
-- Скопируйте ВЕСЬ этот текст и вставьте в Supabase SQL Editor
-- Нажмите RUN (или Ctrl+Enter)
-- ============================================================

-- ============================================================
-- 019: Security fixes
-- ============================================================

-- 1. execute_sql — удаляем опасную функцию
DROP FUNCTION IF EXISTS public.execute_sql CASCADE;

-- 2. handle_new_user — revoke EXECUTE для anon/authenticated
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon, authenticated;

-- 3. st_estimatedextent — revoke EXECUTE
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated;

-- 4. Storage bucket policies — безопасные SELECT
DROP POLICY IF EXISTS "Public read avatars" ON storage.objects;
CREATE POLICY "Public read avatars" ON storage.objects
    FOR SELECT USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] IS NOT NULL);

DROP POLICY IF EXISTS "Public read jobs photos" ON storage.objects;
CREATE POLICY "Public read jobs photos" ON storage.objects
    FOR SELECT USING (bucket_id = 'jobs' AND (storage.foldername(name))[1] IS NOT NULL);

-- ============================================================
-- 020: Performance — RLS initplan + duplicate policies
-- Все операции обёрнуты в DO блоки для обработки ошибок
-- (некоторые таблицы/колонки могут отсутствовать)
-- ============================================================

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users can insert own profile" ON public.profiles;
    CREATE POLICY "Users can insert own profile" ON public.profiles FOR INSERT WITH CHECK ((select auth.uid()) = id);
    DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
    CREATE POLICY "Users can update own profile" ON public.profiles FOR UPDATE USING ((select auth.uid()) = id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'profiles: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Employers can update own details" ON public.employer_details;
    CREATE POLICY "Employers can update own details" ON public.employer_details FOR UPDATE USING ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Employers can insert own details" ON public.employer_details;
    CREATE POLICY "Employers can insert own details" ON public.employer_details FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'employer_details: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Employers can update own jobs" ON public.jobs;
    CREATE POLICY "Employers can update own jobs" ON public.jobs FOR UPDATE USING ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Employers can delete own jobs" ON public.jobs;
    CREATE POLICY "Employers can delete own jobs" ON public.jobs FOR DELETE USING ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Employers can insert jobs" ON public.jobs;
    CREATE POLICY "Employers can insert jobs" ON public.jobs FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Users can read jobs" ON public.jobs;
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'jobs: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Employers can insert job photos" ON public.job_photos;
    CREATE POLICY "Employers can insert job photos" ON public.job_photos FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'job_photos: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users manage own job favorites" ON public.job_favorites;
    CREATE POLICY "Users manage own job favorites" ON public.job_favorites FOR ALL USING ((select auth.uid()) = user_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'job_favorites: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Workers can insert applications" ON public.applications;
    CREATE POLICY "Workers can insert applications" ON public.applications FOR INSERT WITH CHECK ((select auth.uid()) = worker_id);
    DROP POLICY IF EXISTS "Users can view own applications" ON public.applications;
    CREATE POLICY "Users can view own applications" ON public.applications FOR SELECT USING ((select auth.uid()) IN (worker_id, employer_id));
    DROP POLICY IF EXISTS "Employers can update applications" ON public.applications;
    CREATE POLICY "Employers can update applications" ON public.applications FOR UPDATE USING ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Workers can delete own applications" ON public.applications;
    CREATE POLICY "Workers can delete own applications" ON public.applications FOR DELETE USING ((select auth.uid()) = worker_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'applications: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Shift participants can view shifts" ON public.shifts;
    CREATE POLICY "Shift participants can view shifts" ON public.shifts FOR SELECT USING ((select auth.uid()) IN (worker_id, employer_id));
    DROP POLICY IF EXISTS "Shift participants can update shifts" ON public.shifts;
    CREATE POLICY "Shift participants can update shifts" ON public.shifts FOR UPDATE USING ((select auth.uid()) IN (worker_id, employer_id));
    DROP POLICY IF EXISTS "Employers can insert shifts" ON public.shifts;
    CREATE POLICY "Employers can insert shifts" ON public.shifts FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Users can update their own shifts" ON public.shifts;
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'shifts: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Shift participants can view messages" ON public.messages;
    CREATE POLICY "Shift participants can view messages" ON public.messages FOR SELECT USING ((select auth.uid()) IN (sender_id, recipient_id));
    DROP POLICY IF EXISTS "Shift participants can insert messages" ON public.messages;
    CREATE POLICY "Shift participants can insert messages" ON public.messages FOR INSERT WITH CHECK ((select auth.uid()) = sender_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'messages: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users can insert reviews" ON public.reviews;
    CREATE POLICY "Users can insert reviews" ON public.reviews FOR INSERT WITH CHECK ((select auth.uid()) = rater_id);
    DROP POLICY IF EXISTS "Users can update own reviews" ON public.reviews;
    CREATE POLICY "Users can update own reviews" ON public.reviews FOR UPDATE USING ((select auth.uid()) = rater_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'reviews: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users manage own favorites" ON public.favorites;
    CREATE POLICY "Users manage own favorites" ON public.favorites FOR ALL USING ((select auth.uid()) = user_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'favorites: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users manage own blacklists" ON public.blacklists;
    CREATE POLICY "Users manage own blacklists" ON public.blacklists FOR ALL USING ((select auth.uid()) = user_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'blacklists: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users can view own notifications" ON public.notifications;
    CREATE POLICY "Users can view own notifications" ON public.notifications FOR SELECT USING ((select auth.uid()) = user_id);
    DROP POLICY IF EXISTS "Users can update own notifications" ON public.notifications;
    CREATE POLICY "Users can update own notifications" ON public.notifications FOR UPDATE USING ((select auth.uid()) = user_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'notifications: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "monetization_settings_insert" ON public.monetization_settings;
    CREATE POLICY "monetization_settings_insert" ON public.monetization_settings FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "monetization_settings_update" ON public.monetization_settings;
    CREATE POLICY "monetization_settings_update" ON public.monetization_settings FOR UPDATE USING ((select auth.uid()) = employer_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'monetization_settings: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "contact_payments_select" ON public.contact_payments;
    CREATE POLICY "contact_payments_select" ON public.contact_payments FOR SELECT USING ((select auth.uid()) IN (employer_id, worker_id));
    DROP POLICY IF EXISTS "contact_payments_insert" ON public.contact_payments;
    CREATE POLICY "contact_payments_insert" ON public.contact_payments FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "contact_payments_update" ON public.contact_payments;
    CREATE POLICY "contact_payments_update" ON public.contact_payments FOR UPDATE USING ((select auth.uid()) = employer_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'contact_payments: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "receipts_select" ON public.receipts;
    CREATE POLICY "receipts_select" ON public.receipts FOR SELECT USING ((select auth.uid()) = user_id);
    DROP POLICY IF EXISTS "receipts_insert" ON public.receipts;
    CREATE POLICY "receipts_insert" ON public.receipts FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
    DROP POLICY IF EXISTS "receipts_update" ON public.receipts;
    CREATE POLICY "receipts_update" ON public.receipts FOR UPDATE USING ((select auth.uid()) = user_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'receipts: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "hires_select" ON public.hires;
    CREATE POLICY "hires_select" ON public.hires FOR SELECT USING ((select auth.uid()) IN (employer_id, worker_id));
    DROP POLICY IF EXISTS "hires_insert" ON public.hires;
    CREATE POLICY "hires_insert" ON public.hires FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'hires: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Employers can insert invitations" ON public.invitations;
    CREATE POLICY "Employers can insert invitations" ON public.invitations FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
    DROP POLICY IF EXISTS "Users can read their invitations" ON public.invitations;
    CREATE POLICY "Users can read their invitations" ON public.invitations FOR SELECT USING ((select auth.uid()) IN (employer_id, worker_id));
    DROP POLICY IF EXISTS "Workers can update invitations" ON public.invitations;
    CREATE POLICY "Workers can update invitations" ON public.invitations FOR UPDATE USING ((select auth.uid()) = worker_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'invitations: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users can insert own ratings" ON public.ratings;
    CREATE POLICY "Users can insert own ratings" ON public.ratings FOR INSERT WITH CHECK ((select auth.uid()) = rater_user_id);
    DROP POLICY IF EXISTS "Users can update own ratings" ON public.ratings;
    CREATE POLICY "Users can update own ratings" ON public.ratings FOR UPDATE USING ((select auth.uid()) = rater_user_id);
    DROP POLICY IF EXISTS "Users can upsert own ratings" ON public.ratings;
    DROP POLICY IF EXISTS "Users can view ratings" ON public.ratings;
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'ratings: %', SQLERRM; END $$;

DO $$ BEGIN
    DROP POLICY IF EXISTS "Users can view own push subscriptions" ON public.push_subscriptions;
    CREATE POLICY "Users can view own push subscriptions" ON public.push_subscriptions FOR SELECT USING ((select auth.uid()) = user_id);
    DROP POLICY IF EXISTS "Users can insert own push subscriptions" ON public.push_subscriptions;
    CREATE POLICY "Users can insert own push subscriptions" ON public.push_subscriptions FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
    DROP POLICY IF EXISTS "Users can delete own push subscriptions" ON public.push_subscriptions;
    CREATE POLICY "Users can delete own push subscriptions" ON public.push_subscriptions FOR DELETE USING ((select auth.uid()) = user_id);
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'push_subscriptions: %', SQLERRM; END $$;

-- Remove duplicate policies (multiple_permissive_policies fix)
DO $$ BEGIN DROP POLICY IF EXISTS "employer_job_skills" ON public.job_skills; EXCEPTION WHEN OTHERS THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Users can upsert own ratings" ON public.ratings; EXCEPTION WHEN OTHERS THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "Users can view ratings" ON public.ratings; EXCEPTION WHEN OTHERS THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "admin_religions" ON public.religions; EXCEPTION WHEN OTHERS THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "admin_skills" ON public.skills; EXCEPTION WHEN OTHERS THEN NULL; END $$;
DO $$ BEGIN DROP POLICY IF EXISTS "user_own_skills" ON public.user_skills; EXCEPTION WHEN OTHERS THEN NULL; END $$;

-- ============================================================
-- 021: Performance — indexes
-- ============================================================

-- Foreign key indexes
CREATE INDEX IF NOT EXISTS idx_applications_contact_payment_id ON public.applications(contact_payment_id);
CREATE INDEX IF NOT EXISTS idx_applications_worker_id ON public.applications(worker_id);
CREATE INDEX IF NOT EXISTS idx_blacklists_blocked_user_id ON public.blacklists(blocked_user_id);
CREATE INDEX IF NOT EXISTS idx_contact_payments_application_id ON public.contact_payments(application_id);
CREATE INDEX IF NOT EXISTS idx_favorites_target_id ON public.favorites(target_id);
CREATE INDEX IF NOT EXISTS idx_hires_job_id ON public.hires(job_id);
CREATE INDEX IF NOT EXISTS idx_hires_shift_id ON public.hires(shift_id);
CREATE INDEX IF NOT EXISTS idx_hires_worker_id ON public.hires(worker_id);
CREATE INDEX IF NOT EXISTS idx_job_favorites_job_id ON public.job_favorites(job_id);
CREATE INDEX IF NOT EXISTS idx_job_photos_job_id ON public.job_photos(job_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_skill_id ON public.job_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON public.messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_shift_id ON public.messages(shift_id);
CREATE INDEX IF NOT EXISTS idx_profiles_religion_id ON public.profiles(religion_id);
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON public.push_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_shift_id ON public.ratings(shift_id);
CREATE INDEX IF NOT EXISTS idx_receipts_contact_payment_id ON public.receipts(contact_payment_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewee_id ON public.reviews(reviewee_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer_id ON public.reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_shift_id ON public.reviews(shift_id);
CREATE INDEX IF NOT EXISTS idx_shifts_employer_id ON public.shifts(employer_id);
CREATE INDEX IF NOT EXISTS idx_shifts_job_id ON public.shifts(job_id);
CREATE INDEX IF NOT EXISTS idx_shifts_worker_id ON public.shifts(worker_id);
CREATE INDEX IF NOT EXISTS idx_user_skills_skill_id ON public.user_skills(skill_id);

-- Drop unused indexes
DROP INDEX IF EXISTS public.idx_jobs_search;
DROP INDEX IF EXISTS public.idx_profiles_search;
DROP INDEX IF EXISTS public.idx_jobs_status;
DROP INDEX IF EXISTS public.idx_jobs_current_workers;
DROP INDEX IF EXISTS public.idx_jobs_status_and_workers;
DROP INDEX IF EXISTS public.idx_notifications_read;
DROP INDEX IF EXISTS public.idx_notifications_created;
DROP INDEX IF EXISTS public.idx_hires_pair;
DROP INDEX IF EXISTS public.idx_hires_date;

-- ============================================================
-- ГОТОВО! После выполнения обновите Security Advisor
-- ============================================================


-- ============================================================
-- 038_fix_unpaid_jobs: Mark all open jobs as paid
-- ============================================================
-- Fix: mark all open jobs as paid so they become visible again
-- The payment pipeline is not yet implemented, so all jobs should be visible
UPDATE jobs 
SET is_paid = TRUE,
    paid_at = NOW(),
    expires_at = NOW() + INTERVAL '30 days'
WHERE status IN ('open', 'completed') 
  AND (is_paid = FALSE OR is_paid IS NULL);


-- ============================================================
-- 039_atomic_operations: RPC-процедуры
-- Полный SQL — в файле migrations/039_atomic_operations.sql
-- Создаёт функции: accept_application, reject_application,
--                  delete_job_cascade, delete_user_cascade
-- Все с SECURITY DEFINER, атомарные операции
-- ============================================================
-- ⚠ Запустите migrations/039_atomic_operations.sql отдельно
--    (файл слишком большой для включения сюда)


-- ============================================================
-- 040: Schema Versioning
-- ============================================================

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
VALUES ('040', 'Schema versioning: таблица schema_migrations с RLS')
ON CONFLICT (version) DO NOTHING;


-- ============================================================
-- 041: FK для messages — sender_id → profiles.id ON DELETE CASCADE
-- ============================================================

-- FK: messages.sender_id → profiles.id
DO $$
DECLARE
    fk_exists boolean;
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

    IF NOT fk_exists THEN
        DELETE FROM messages
        WHERE sender_id IS NOT NULL
          AND sender_id NOT IN (SELECT id FROM profiles);

        ALTER TABLE public.messages
            ADD CONSTRAINT fk_messages_sender_id
            FOREIGN KEY (sender_id)
            REFERENCES public.profiles(id)
            ON DELETE CASCADE;

        RAISE NOTICE 'FK messages.sender_id → profiles.id created';
    ELSE
        RAISE NOTICE 'FK messages.sender_id → profiles.id already exists';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'FK messages.sender_id: %', SQLERRM;
END $$;

-- FK: messages.application_id → applications.id
DO $$
DECLARE
    fk_exists boolean;
    col_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages'
          AND column_name = 'application_id'
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

        IF NOT fk_exists THEN
            DELETE FROM messages
            WHERE application_id IS NOT NULL
              AND application_id NOT IN (SELECT id FROM applications);

            ALTER TABLE public.messages
                ADD CONSTRAINT fk_messages_application_id
                FOREIGN KEY (application_id)
                REFERENCES public.applications(id)
                ON DELETE CASCADE;

            RAISE NOTICE 'FK messages.application_id → applications.id created';
        ELSE
            RAISE NOTICE 'FK messages.application_id → applications.id already exists';
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


-- ============================================================
-- 042: Чистка дубликатов и мёртвых таблиц
-- ============================================================

-- Дубликаты: notifications.read vs is_read
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
        UPDATE notifications
        SET is_read = read::boolean
        WHERE is_read IS NULL AND read IS NOT NULL;

        ALTER TABLE public.notifications DROP COLUMN IF EXISTS read;
        RAISE NOTICE 'notifications: колонка read удалена (оставлена is_read)';
    ELSIF has_read AND NOT has_is_read THEN
        ALTER TABLE public.notifications RENAME COLUMN read TO is_read;
        RAISE NOTICE 'notifications: колонка read переименована в is_read';
    ELSE
        RAISE NOTICE 'notifications: дубликатов нет';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'notifications cleanup: %', SQLERRM;
END $$;

-- Дубликаты: profiles.religion (TEXT) vs religion_id (UUID)
DO $$
BEGIN
    COMMENT ON COLUMN public.profiles.religion IS 'DEPRECATED: используйте religion_id (UUID → religions.id)';
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Мёртвые таблицы
DO $$ BEGIN
    COMMENT ON TABLE public.shifts IS 'DEPRECATED: заменены на application-based чат (messages.application_id). Миграция 027.';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

DO $$ BEGIN
    COMMENT ON TABLE public.spatial_ref_sys IS 'DEPRECATED: системная таблица PostGIS, не используется приложением.';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

INSERT INTO public.schema_migrations (version, description)
VALUES ('042', 'Cleanup: дубликаты колонок, пометка мёртвых таблиц')
ON CONFLICT (version) DO NOTHING;
