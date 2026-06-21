-- ============================================================================
-- Миграция 057: Исправление предупреждений Supabase Security Linter (v3)
-- Дата: 2026-06-21
-- Контекст: 22 WARNING + 5 INFO от Supabase Database Linter
-- ============================================================================

BEGIN;

-- ═══════════════════════════════════════════════════════
-- Часть 1: RLS политики — замена USING/WITH CHECK (true) на проверку роли
-- ═══════════════════════════════════════════════════════
--
-- Анализ: функция is_admin() не найдена в миграциях. В миграции 007
-- используется паттерн:
--   EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin')
-- Этот же паттерн применяем здесь для консистентности.

-- 1a. religions — INSERT (WITH CHECK)
DROP POLICY IF EXISTS "Admin can insert religions" ON public.religions;
CREATE POLICY "Admin can insert religions" ON public.religions
    FOR INSERT
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- 1b. religions — UPDATE (USING + WITH CHECK)
DROP POLICY IF EXISTS "Admin can update religions" ON public.religions;
CREATE POLICY "Admin can update religions" ON public.religions
    FOR UPDATE
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'))
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- 1c. religions — DELETE (USING)
DROP POLICY IF EXISTS "Admin can delete religions" ON public.religions;
CREATE POLICY "Admin can delete religions" ON public.religions
    FOR DELETE
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- 1d. skills — INSERT (WITH CHECK)
DROP POLICY IF EXISTS "Admin can insert skills" ON public.skills;
CREATE POLICY "Admin can insert skills" ON public.skills
    FOR INSERT
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- 1e. skills — UPDATE (USING + WITH CHECK)
DROP POLICY IF EXISTS "Admin can update skills" ON public.skills;
CREATE POLICY "Admin can update skills" ON public.skills
    FOR UPDATE
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'))
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- 1f. skills — DELETE (USING)
DROP POLICY IF EXISTS "Admin can delete skills" ON public.skills;
CREATE POLICY "Admin can delete skills" ON public.skills
    FOR DELETE
    USING (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- 1g. notifications — INSERT (WITH CHECK)
-- Разрешаем вставку уведомлений только админам через RLS.
-- service_role обходит RLS по определению, поэтому дополнительная проверка не нужна.
DROP POLICY IF EXISTS "Service can insert notifications" ON public.notifications;
CREATE POLICY "Service can insert notifications" ON public.notifications
    FOR INSERT
    WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'));

-- ═══════════════════════════════════════════════════════
-- Часть 2: REVOKE EXECUTE от anon для SECURITY DEFINER функций
-- ═══════════════════════════════════════════════════════

-- apply_job_atomic — атомарное создание отклика (миграция 048).
-- Функция вызывается из Flask с JWT-токеном пользователя (authenticated)
-- или через service_role. Анонимы не должны иметь доступ.
REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) FROM anon, PUBLIC;

-- ═══════════════════════════════════════════════════════
-- Часть 3: Удаление неиспользуемых индексов (5 INFO)
-- ═══════════════════════════════════════════════════════

DROP INDEX IF EXISTS idx_favorites_target_id;
DROP INDEX IF EXISTS idx_profiles_religion_id;
DROP INDEX IF EXISTS idx_receipts_contact_payment_id;
DROP INDEX IF EXISTS idx_push_subscriptions_endpoint;
DROP INDEX IF EXISTS idx_email_log_status;

-- ═══════════════════════════════════════════════════════
-- Часть 4: Осознанные исключения (не трогаем, только документируем)
-- ═══════════════════════════════════════════════════════

-- 4a. Расширения в public схеме (postgis, cube, earthdistance)
--     Стандартное поведение PostGIS: расширения устанавливаются в public.
--     Перемещение может сломать геопространственные функции (nearby_jobs и др.).
--     Это осознанное решение, подтверждённое в миграциях 025, 031, 047.

DO $$
BEGIN
    RAISE WARNING 'postgis, cube, earthdistance extensions remain in public schema — standard PostGIS behaviour, relocation would break geospatial functions.';
END $$;

-- 4b. SECURITY DEFINER RPC функции (accept_application, reject_application,
--     apply_job_atomic, nearby_jobs, delete_job_cascade, delete_user_cascade)
--     Эти функции ПОЛНОСТЬЮ преднамеренно используют SECURITY DEFINER
--     для обхода RLS. Внутри каждой функции есть проверки прав:
--     - accept_application/reject_application: проверяют employer_id задания
--     - apply_job_atomic: проверяет статус задания, лимиты, блокировки
--     - nearby_jobs: читает геоданные, требует обхода RLS для поиска
--     - delete_job_cascade/delete_user_cascade: вызываются только через service_role
--     Доступ authenticated пользователей к accept_application, reject_application,
--     apply_job_atomic и nearby_jobs — осознанное решение.
--     REVOKE от anon уже выполнен в миграции 047, для apply_job_atomic — в этой миграции.

DO $$
BEGIN
    RAISE WARNING 'SECURITY DEFINER functions (accept_application, reject_application, apply_job_atomic, nearby_jobs) intentionally accessible to authenticated users — internal permission checks validate ownership.';
END $$;

-- 4c. st_estimatedextent (3 перегрузки)
--     Функция расширения PostGIS. Не может быть изменена или удалена.
--     REVOKE от anon/authenticated выполнен в миграции 047.

DO $$
BEGIN
    RAISE WARNING 'st_estimatedextent (PostGIS) — REVOKE from anon/authenticated already done in migration 047. Cannot be modified further.';
END $$;

-- 4d. auth_leaked_password_protection
--     Проверка утёкших паролей через HaveIBeenPwned отключена.
--     Это НЕ SQL-миграция. Нужно включить вручную:
--     Supabase Dashboard → Authentication → Settings → Enable leaked password protection.

DO $$
BEGIN
    RAISE WARNING 'Leaked password protection (HaveIBeenPwned) must be enabled manually: Supabase Dashboard → Authentication → Settings → Password Protection → Enable leaked password protection.';
END $$;

COMMIT;
