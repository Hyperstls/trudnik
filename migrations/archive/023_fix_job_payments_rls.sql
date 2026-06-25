-- ============================================================================
-- Миграция: Исправление RLS-политик для job_payments
-- Проблема: политика "Service can insert payments" имела WITH CHECK (true)
-- что позволяло кому угодно вставлять записи.
-- Актуально на: 12.06.2026
-- ============================================================================

-- Фикс: ограничить INSERT только авторизованными пользователями
DROP POLICY IF EXISTS "Service can insert payments" ON job_payments;
CREATE POLICY "Service can insert payments" ON job_payments
    FOR INSERT WITH CHECK (auth.role() = 'authenticated');
