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
-- ============================================================

-- profiles
DROP POLICY IF EXISTS "Users can insert own profile" ON public.profiles;
CREATE POLICY "Users can insert own profile" ON public.profiles
    FOR INSERT WITH CHECK ((select auth.uid()) = id);
DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE USING ((select auth.uid()) = id);

-- employer_details
DROP POLICY IF EXISTS "Employers can update own details" ON public.employer_details;
CREATE POLICY "Employers can update own details" ON public.employer_details
    FOR UPDATE USING ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Employers can insert own details" ON public.employer_details;
CREATE POLICY "Employers can insert own details" ON public.employer_details
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);

-- jobs
DROP POLICY IF EXISTS "Employers can update own jobs" ON public.jobs;
CREATE POLICY "Employers can update own jobs" ON public.jobs
    FOR UPDATE USING ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Employers can delete own jobs" ON public.jobs;
CREATE POLICY "Employers can delete own jobs" ON public.jobs
    FOR DELETE USING ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Employers can insert jobs" ON public.jobs;
CREATE POLICY "Employers can insert jobs" ON public.jobs
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Users can read jobs" ON public.jobs;

-- job_photos
DROP POLICY IF EXISTS "Employers can insert job photos" ON public.job_photos;
CREATE POLICY "Employers can insert job photos" ON public.job_photos
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);

-- job_favorites
DROP POLICY IF EXISTS "Users manage own job favorites" ON public.job_favorites;
CREATE POLICY "Users manage own job favorites" ON public.job_favorites
    FOR ALL USING ((select auth.uid()) = user_id);

-- applications
DROP POLICY IF EXISTS "Workers can insert applications" ON public.applications;
CREATE POLICY "Workers can insert applications" ON public.applications
    FOR INSERT WITH CHECK ((select auth.uid()) = worker_id);
DROP POLICY IF EXISTS "Users can view own applications" ON public.applications;
CREATE POLICY "Users can view own applications" ON public.applications
    FOR SELECT USING ((select auth.uid()) IN (worker_id, employer_id));
DROP POLICY IF EXISTS "Employers can update applications" ON public.applications;
CREATE POLICY "Employers can update applications" ON public.applications
    FOR UPDATE USING ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Workers can delete own applications" ON public.applications;
CREATE POLICY "Workers can delete own applications" ON public.applications
    FOR DELETE USING ((select auth.uid()) = worker_id);

-- shifts
DROP POLICY IF EXISTS "Shift participants can view shifts" ON public.shifts;
CREATE POLICY "Shift participants can view shifts" ON public.shifts
    FOR SELECT USING ((select auth.uid()) IN (worker_id, employer_id));
DROP POLICY IF EXISTS "Shift participants can update shifts" ON public.shifts;
CREATE POLICY "Shift participants can update shifts" ON public.shifts
    FOR UPDATE USING ((select auth.uid()) IN (worker_id, employer_id));
DROP POLICY IF EXISTS "Employers can insert shifts" ON public.shifts;
CREATE POLICY "Employers can insert shifts" ON public.shifts
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Users can update their own shifts" ON public.shifts;

-- messages
DROP POLICY IF EXISTS "Shift participants can view messages" ON public.messages;
CREATE POLICY "Shift participants can view messages" ON public.messages
    FOR SELECT USING ((select auth.uid()) IN (sender_id, recipient_id));
DROP POLICY IF EXISTS "Shift participants can insert messages" ON public.messages;
CREATE POLICY "Shift participants can insert messages" ON public.messages
    FOR INSERT WITH CHECK ((select auth.uid()) = sender_id);

-- reviews
DROP POLICY IF EXISTS "Users can insert reviews" ON public.reviews;
CREATE POLICY "Users can insert reviews" ON public.reviews
    FOR INSERT WITH CHECK ((select auth.uid()) = rater_id);
DROP POLICY IF EXISTS "Users can update own reviews" ON public.reviews;
CREATE POLICY "Users can update own reviews" ON public.reviews
    FOR UPDATE USING ((select auth.uid()) = rater_id);

-- favorites
DROP POLICY IF EXISTS "Users manage own favorites" ON public.favorites;
CREATE POLICY "Users manage own favorites" ON public.favorites
    FOR ALL USING ((select auth.uid()) = user_id);

-- blacklists
DROP POLICY IF EXISTS "Users manage own blacklists" ON public.blacklists;
CREATE POLICY "Users manage own blacklists" ON public.blacklists
    FOR ALL USING ((select auth.uid()) = user_id);

-- notifications
DROP POLICY IF EXISTS "Users can view own notifications" ON public.notifications;
CREATE POLICY "Users can view own notifications" ON public.notifications
    FOR SELECT USING ((select auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users can update own notifications" ON public.notifications;
CREATE POLICY "Users can update own notifications" ON public.notifications
    FOR UPDATE USING ((select auth.uid()) = user_id);

-- monetization_settings
DROP POLICY IF EXISTS "monetization_settings_insert" ON public.monetization_settings;
CREATE POLICY "monetization_settings_insert" ON public.monetization_settings
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "monetization_settings_update" ON public.monetization_settings;
CREATE POLICY "monetization_settings_update" ON public.monetization_settings
    FOR UPDATE USING ((select auth.uid()) = employer_id);

-- contact_payments
DROP POLICY IF EXISTS "contact_payments_select" ON public.contact_payments;
CREATE POLICY "contact_payments_select" ON public.contact_payments
    FOR SELECT USING ((select auth.uid()) IN (employer_id, worker_id));
DROP POLICY IF EXISTS "contact_payments_insert" ON public.contact_payments;
CREATE POLICY "contact_payments_insert" ON public.contact_payments
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "contact_payments_update" ON public.contact_payments;
CREATE POLICY "contact_payments_update" ON public.contact_payments
    FOR UPDATE USING ((select auth.uid()) = employer_id);

-- receipts
DROP POLICY IF EXISTS "receipts_select" ON public.receipts;
CREATE POLICY "receipts_select" ON public.receipts
    FOR SELECT USING ((select auth.uid()) = user_id);
DROP POLICY IF EXISTS "receipts_insert" ON public.receipts;
CREATE POLICY "receipts_insert" ON public.receipts
    FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
DROP POLICY IF EXISTS "receipts_update" ON public.receipts;
CREATE POLICY "receipts_update" ON public.receipts
    FOR UPDATE USING ((select auth.uid()) = user_id);

-- hires
DROP POLICY IF EXISTS "hires_select" ON public.hires;
CREATE POLICY "hires_select" ON public.hires
    FOR SELECT USING ((select auth.uid()) IN (employer_id, worker_id));
DROP POLICY IF EXISTS "hires_insert" ON public.hires;
CREATE POLICY "hires_insert" ON public.hires
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);

-- invitations
DROP POLICY IF EXISTS "Employers can insert invitations" ON public.invitations;
CREATE POLICY "Employers can insert invitations" ON public.invitations
    FOR INSERT WITH CHECK ((select auth.uid()) = employer_id);
DROP POLICY IF EXISTS "Users can read their invitations" ON public.invitations;
CREATE POLICY "Users can read their invitations" ON public.invitations
    FOR SELECT USING ((select auth.uid()) IN (employer_id, worker_id));
DROP POLICY IF EXISTS "Workers can update invitations" ON public.invitations;
CREATE POLICY "Workers can update invitations" ON public.invitations
    FOR UPDATE USING ((select auth.uid()) = worker_id);

-- ratings
DROP POLICY IF EXISTS "Users can insert own ratings" ON public.ratings;
CREATE POLICY "Users can insert own ratings" ON public.ratings
    FOR INSERT WITH CHECK ((select auth.uid()) = rater_user_id);
DROP POLICY IF EXISTS "Users can update own ratings" ON public.ratings;
CREATE POLICY "Users can update own ratings" ON public.ratings
    FOR UPDATE USING ((select auth.uid()) = rater_user_id);
DROP POLICY IF EXISTS "Users can upsert own ratings" ON public.ratings;
DROP POLICY IF EXISTS "Users can view ratings" ON public.ratings;

-- push_subscriptions
DROP POLICY IF EXISTS "Users can view own push subscriptions" ON public.push_subscriptions;
CREATE POLICY "Users can view own push subscriptions" ON public.push_subscriptions
    FOR SELECT USING ((select auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users can insert own push subscriptions" ON public.push_subscriptions;
CREATE POLICY "Users can insert own push subscriptions" ON public.push_subscriptions
    FOR INSERT WITH CHECK ((select auth.uid()) = user_id);
DROP POLICY IF EXISTS "Users can delete own push subscriptions" ON public.push_subscriptions;
CREATE POLICY "Users can delete own push subscriptions" ON public.push_subscriptions
    FOR DELETE USING ((select auth.uid()) = user_id);

-- Remove duplicate policies (multiple_permissive_policies fix)
DROP POLICY IF EXISTS "employer_job_skills" ON public.job_skills;
DROP POLICY IF EXISTS "Users can upsert own ratings" ON public.ratings;
DROP POLICY IF EXISTS "Users can view ratings" ON public.ratings;
DROP POLICY IF EXISTS "admin_religions" ON public.religions;
DROP POLICY IF EXISTS "admin_skills" ON public.skills;
DROP POLICY IF EXISTS "user_own_skills" ON public.user_skills;

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
