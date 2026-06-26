-- ============================================================================
-- Миграция 073: Исправление RLS-политик для admin-операций с skills/religions
-- Файл: migrations/073_fix_admin_rls_policies.sql
-- Дата: 2026-06-26
-- ============================================================================
--
-- ПРОБЛЕМА:
--   postgrest_admin_request() создаёт JWT с ролью 'trudnikapp' (см. postgrest_client.py,
--   функция get_service_role_headers). Однако RLS-политики admin_skills и
--   admin_religions проверяют current_setting('request.jwt.claim.role', true) = 'admin'.
--   Из-за несовпадения ролей PostgREST отклоняет INSERT (HTTP 403), и данные
--   не сохраняются, хотя Flask-код делает редирект (HTTP 302) с flash-сообщением.
--
-- РЕШЕНИЕ:
--   Добавить роль 'trudnikapp' в RLS-политики для admin_skills и admin_religions.
--   Также затронуты политики receipts_insert и receipts_update (аналогичная проблема).
--
-- ВАЖНО:
--   Если в будущем роль в JWT изменится, политики нужно будет обновить синхронно.
-- ============================================================================

BEGIN;

-- ============================================
-- 1. skills — политика admin_skills
-- ============================================
DROP POLICY IF EXISTS "admin_skills" ON skills;
CREATE POLICY "admin_skills" ON skills FOR ALL
    USING (current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp'));

-- ============================================
-- 2. religions — политика admin_religions
-- ============================================
DROP POLICY IF EXISTS "admin_religions" ON religions;
CREATE POLICY "admin_religions" ON religions FOR ALL
    USING (current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp'));

-- ============================================
-- 3. receipts — политики вставки/обновления
--    (аналогичная проблема — postgrest_admin_request не может
--    вставлять/обновлять receipts)
-- ============================================
DROP POLICY IF EXISTS "receipts_insert" ON receipts;
CREATE POLICY "receipts_insert" ON receipts
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp')
    );

DROP POLICY IF EXISTS "receipts_update" ON receipts;
CREATE POLICY "receipts_update" ON receipts
    FOR UPDATE USING (
        current_setting('request.jwt.claim.role', true) IN ('admin', 'trudnikapp')
    );

COMMIT;

-- ============================================================================
-- ПРОВЕРКА:
--   SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
--   FROM pg_policies
--   WHERE tablename IN ('skills', 'religions', 'receipts')
--   ORDER BY tablename, policyname;
-- ============================================================================
