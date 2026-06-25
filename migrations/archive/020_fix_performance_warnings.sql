-- ============================================================
-- Миграция: исправление PERFORMANCE warnings
-- auth_rls_initplan + multiple_permissive_policies
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- ============================================================
-- 1. auth_rls_initplan: заменить auth.uid() на (select auth.uid())
-- во всех RLS политиках.
-- Это позволяет PostgreSQL использовать INITPLAN (однократное
-- вычисление auth.uid() для всего запроса, а не для каждой строки).
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

-- reviews (ratings table)
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
-- upsert policy is redundant with insert + update, and causes multiple_permissive_policies

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

-- ============================================================
-- 2. multiple_permissive_policies: удалить дублирующиеся политики
-- ============================================================

-- job_skills: employer_job_skills и read_job_skills обе на SELECT
-- Оставляем read_job_skills (более общая)
DROP POLICY IF EXISTS "employer_job_skills" ON public.job_skills;

-- jobs: "Jobs are viewable by everyone" и "Users can read jobs" обе на SELECT
-- Оставляем "Jobs are viewable by everyone" (более общая)
DROP POLICY IF EXISTS "Users can read jobs" ON public.jobs;

-- ratings: "Users can upsert own ratings" дублирует INSERT и UPDATE
DROP POLICY IF EXISTS "Users can upsert own ratings" ON public.ratings;

-- ratings: "Anyone can read ratings" и "Users can view ratings" дублируют SELECT
DROP POLICY IF EXISTS "Users can view ratings" ON public.ratings;

-- religions: admin_religions и read_religions обе на SELECT
DROP POLICY IF EXISTS "admin_religions" ON public.religions;

-- skills: admin_skills и read_skills обе на SELECT
DROP POLICY IF EXISTS "admin_skills" ON public.skills;

-- shifts: "Shift participants can update shifts" и "Users can update their own shifts"
-- "Users can update their own shifts" уже удалена выше при auth_rls_initplan

-- user_skills: read_user_skills и user_own_skills обе на SELECT
DROP POLICY IF EXISTS "user_own_skills" ON public.user_skills;
