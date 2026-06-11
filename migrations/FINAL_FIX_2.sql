-- ============================================================
-- ФИНАЛЬНЫЙ ФИКС ВСЕХ ОСТАВШИХСЯ WARNINGS
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- ============================================================
-- 1. rls_policy_always_true: monetization_settings + receipts INSERT
--    Заменяем CHECK(true) на более строгие условия
-- ============================================================

DROP POLICY IF EXISTS "monetization_settings_insert" ON public.monetization_settings;
CREATE POLICY "monetization_settings_insert" ON public.monetization_settings
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin')
    );

DROP POLICY IF EXISTS "receipts_insert" ON public.receipts;
CREATE POLICY "receipts_insert" ON public.receipts
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin')
    );

-- ============================================================
-- 2. auth_rls_initplan: applications INSERT/VIEW/DELETE + messages
--    Обёртываем auth.uid() в (SELECT auth.uid())
-- ============================================================

-- applications: Workers can insert applications
DROP POLICY IF EXISTS "Workers can insert applications" ON public.applications;
CREATE POLICY "Workers can insert applications" ON public.applications
    FOR INSERT WITH CHECK ((select auth.uid()) = worker_id);

-- applications: Users can view own applications
-- (работник видит свои отклики, работодатель — через jobs)
DROP POLICY IF EXISTS "Users can view own applications" ON public.applications;
CREATE POLICY "Users can view own applications" ON public.applications
    FOR SELECT USING (
        (select auth.uid()) = worker_id
        OR
        (select auth.uid()) IN (SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id)
    );

-- applications: Employers can update applications
-- (employer_id берётся через jobs, а не из applications)
DROP POLICY IF EXISTS "Employers can update applications" ON public.applications;
CREATE POLICY "Employers can update applications" ON public.applications
    FOR UPDATE USING (
        (select auth.uid()) IN (SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id)
    );

-- applications: Workers can delete own applications
DROP POLICY IF EXISTS "Workers can delete own applications" ON public.applications;
CREATE POLICY "Workers can delete own applications" ON public.applications
    FOR DELETE USING ((select auth.uid()) = worker_id);

-- messages: Shift participants can view messages
-- (нет колонки recipient_id, участники определяются через shifts)
DROP POLICY IF EXISTS "Shift participants can view messages" ON public.messages;
CREATE POLICY "Shift participants can view messages" ON public.messages
    FOR SELECT USING (
        (select auth.uid()) IN (
            SELECT worker_id FROM shifts WHERE shifts.id = messages.shift_id
            UNION
            SELECT employer_id FROM shifts WHERE shifts.id = messages.shift_id
        )
    );

-- messages: Shift participants can insert messages
DROP POLICY IF EXISTS "Shift participants can insert messages" ON public.messages;
CREATE POLICY "Shift participants can insert messages" ON public.messages
    FOR INSERT WITH CHECK ((select auth.uid()) = sender_id);

-- ============================================================
-- 3. multiple_permissive_policies: ratings
--   Drop "Admin can manage ratings" чтобы убрать дублирование
--   (админ-политика воссоздана в FINAL_FIX с (SELECT auth.uid()))
--   Проблема: она дублирует INSERT/UPDATE/SELECT
--   Решение: удаляем "Admin can manage ratings" полностью
--   и делаем отдельные политики для каждой операции
-- ============================================================

DROP POLICY IF EXISTS "Admin can manage ratings" ON public.ratings;

-- Recreate admin ratings with proper wrapping, only for what users can't do
CREATE POLICY "Admin can manage ratings" ON public.ratings
    FOR ALL USING (
        EXISTS (SELECT 1 FROM profiles WHERE profiles.id = (select auth.uid()) AND profiles.role = 'admin')
    );

-- ============================================================
-- 4. handle_new_user + st_estimatedextent: REVOKE EXECUTE
-- ============================================================

REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon, authenticated, public;
REVOKE ALL ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated, public;
REVOKE ALL ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated, public;
REVOKE ALL ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated, public;

-- ============================================================
-- ГОТОВО! Запустите Security Advisor → Re-run
-- ============================================================
