-- Миграция 025: Исправление предупреждений Supabase Security Linter
-- SECURITY: SECURITY DEFINER + PERFORMANCE: auth_rls_initplan

-- 1. SECURITY DEFINER функции PostGIS — отзываем EXECUTE
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated;

-- 2. PERFORMANCE: оптимизация RLS — (select auth.uid()) вместо auth.uid()

-- job_payments
DROP POLICY IF EXISTS "Employers can read own payments" ON job_payments;
CREATE POLICY "Employers can read own payments" ON job_payments
    FOR SELECT USING ((SELECT auth.uid()) = employer_id);

-- jobs (объединяет фиксы из 024 + оптимизацию)
DROP POLICY IF EXISTS "Jobs are viewable by everyone" ON jobs;
CREATE POLICY "Jobs are viewable by everyone" ON jobs
    FOR SELECT USING (
        status = 'open'
        OR ((SELECT auth.uid()) = employer_id)
        OR (EXISTS (SELECT 1 FROM profiles WHERE id = (SELECT auth.uid()) AND role = 'admin'))
    );

-- applications (объединяет фиксы из 024 + оптимизацию)
DROP POLICY IF EXISTS "Workers can insert applications" ON applications;
CREATE POLICY "Workers can insert applications" ON applications
    FOR INSERT WITH CHECK (
        (SELECT auth.uid()) = worker_id
        AND (SELECT auth.uid()) IS NOT NULL
    );

-- 3. Неиспользуемые индексы (удалить после верификации)
-- DROP INDEX IF EXISTS idx_applications_worker_id;
-- DROP INDEX IF EXISTS idx_favorites_target_id;
-- DROP INDEX IF EXISTS idx_job_skills_skill_id;
-- DROP INDEX IF EXISTS idx_profiles_religion_id;
-- DROP INDEX IF EXISTS idx_receipts_contact_payment_id;
-- DROP INDEX IF EXISTS idx_shifts_employer_id;
-- DROP INDEX IF EXISTS idx_shifts_job_id;
-- DROP INDEX IF EXISTS idx_shifts_worker_id;
-- DROP INDEX IF EXISTS idx_user_skills_skill_id;
-- DROP INDEX IF EXISTS idx_jobs_expires;
-- DROP INDEX IF EXISTS idx_job_payments_job;
