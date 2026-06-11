-- ============================================================
-- ФИНАЛЬНЫЙ ФИКС: исправление оставшихся auth_rls_initplan
-- Основан на реальных RLS-политиках из базы
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- employer_details: колонка id, не employer_id!
DROP POLICY IF EXISTS "Employers can update own details" ON public.employer_details;
CREATE POLICY "Employers can update own details" ON public.employer_details
    FOR UPDATE USING ((select auth.uid()) = id);

DROP POLICY IF EXISTS "Employers can insert own details" ON public.employer_details;
CREATE POLICY "Employers can insert own details" ON public.employer_details
    FOR INSERT WITH CHECK ((select auth.uid()) = id);

-- job_photos: with_check (INSERT) — может не быть employer_id
DO $$ BEGIN
    DROP POLICY IF EXISTS "Employers can insert job photos" ON public.job_photos;
    CREATE POLICY "Employers can insert job photos" ON public.job_photos
        FOR INSERT WITH CHECK ((select auth.uid()) IN (SELECT employer_id FROM jobs WHERE jobs.id = job_id));
EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'job_photos: %', SQLERRM; END $$;

-- monetization_settings: INSERT без auth.uid() в with_check
DROP POLICY IF EXISTS "monetization_settings_insert" ON public.monetization_settings;
CREATE POLICY "monetization_settings_insert" ON public.monetization_settings
    FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "monetization_settings_update" ON public.monetization_settings;
CREATE POLICY "monetization_settings_update" ON public.monetization_settings
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin')
    );

DROP POLICY IF EXISTS "monetization_settings_select" ON public.monetization_settings;
CREATE POLICY "monetization_settings_select" ON public.monetization_settings
    FOR SELECT USING (true);

-- receipts: complex query with auth.uid() IN (...)
DROP POLICY IF EXISTS "receipts_select" ON public.receipts;
CREATE POLICY "receipts_select" ON public.receipts
    FOR SELECT USING (
        ((select auth.uid()) IN (
            SELECT contact_payments.employer_id FROM contact_payments WHERE contact_payments.id = receipts.contact_payment_id
            UNION
            SELECT contact_payments.worker_id FROM contact_payments WHERE contact_payments.id = receipts.contact_payment_id
        ))
        OR
        (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin'))
    );

DROP POLICY IF EXISTS "receipts_insert" ON public.receipts;
CREATE POLICY "receipts_insert" ON public.receipts
    FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "receipts_update" ON public.receipts;
CREATE POLICY "receipts_update" ON public.receipts
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin')
    );

-- reviews: колонка reviewer_id!
DROP POLICY IF EXISTS "Users can insert reviews" ON public.reviews;
CREATE POLICY "Users can insert reviews" ON public.reviews
    FOR INSERT WITH CHECK ((select auth.uid()) = reviewer_id);

DROP POLICY IF EXISTS "Users can update own reviews" ON public.reviews;
CREATE POLICY "Users can update own reviews" ON public.reviews
    FOR UPDATE USING ((select auth.uid()) = reviewer_id);

-- user_skills: auth.uid() IS NOT NULL
DROP POLICY IF EXISTS "read_user_skills" ON public.user_skills;
CREATE POLICY "read_user_skills" ON public.user_skills
    FOR SELECT USING ((select auth.uid()) IS NOT NULL);

-- ratings: Admin can manage ratings (EXISTS + auth.uid())
DROP POLICY IF EXISTS "Admin can manage ratings" ON public.ratings;
CREATE POLICY "Admin can manage ratings" ON public.ratings
    FOR ALL USING (
        EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin')
    );

-- ratings: Users can insert own ratings
DROP POLICY IF EXISTS "Users can insert own ratings" ON public.ratings;
CREATE POLICY "Users can insert own ratings" ON public.ratings
    FOR INSERT WITH CHECK ((select auth.uid()) = rater_user_id);

-- ============================================================
-- ГОТОВО! Запустите Security Advisor → Re-run
-- ============================================================
