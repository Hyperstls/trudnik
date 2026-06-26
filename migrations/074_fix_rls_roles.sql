-- ============================================================================
-- Миграция 074: Добавление TO-клаузы в RLS-политики для admin-операций
-- Файл: migrations/074_fix_rls_roles.sql
-- Дата: 2026-06-26
-- ============================================================================
--
-- ПРОБЛЕМА:
--   Миграция 073 создала политики admin_skills, admin_religions, receipts_insert,
--   receipts_update БЕЗ явной клаузы TO. По умолчанию PostgREST назначает
--   TO public, поэтому pg_policies показывает roles={public}.
--   Из-за этого политики не применяются к роли trudnikapp в JWT, и
--   postgrest_admin_request() получает 403 Forbidden.
--
-- РЕШЕНИЕ:
--   1. Дропнуть все проблемные политики
--   2. Создать их заново с явным TO trudnikapp
--   3. В USING/CHECK использовать current_setting('request.jwt.claim.role', true)
--      для проверки роли из JWT
--
-- ВАЖНО:
--   - read_skills и read_religions НЕ трогаем — они для публичного чтения
--     и должны оставаться без TO (т.е. public)
--   - Роль trudnikapp в JWT устанавливается в postgrest_admin_request()
--     (см. app/utils/postgrest_client.py, функция get_service_role_headers)
-- ============================================================================

BEGIN;

-- ============================================
-- 1. skills — политика admin_skills
-- ============================================
DROP POLICY IF EXISTS "admin_skills" ON skills;
CREATE POLICY "admin_skills" ON skills
    FOR ALL
    TO trudnikapp
    USING (current_setting('request.jwt.claim.role', true) = 'trudnikapp')
    WITH CHECK (current_setting('request.jwt.claim.role', true) = 'trudnikapp');

-- ============================================
-- 2. religions — политика admin_religions
-- ============================================
DROP POLICY IF EXISTS "admin_religions" ON religions;
CREATE POLICY "admin_religions" ON religions
    FOR ALL
    TO trudnikapp
    USING (current_setting('request.jwt.claim.role', true) = 'trudnikapp')
    WITH CHECK (current_setting('request.jwt.claim.role', true) = 'trudnikapp');

-- ============================================
-- 3. receipts — политика receipts_insert
-- ============================================
DROP POLICY IF EXISTS "receipts_insert" ON receipts;
CREATE POLICY "receipts_insert" ON receipts
    FOR INSERT
    TO trudnikapp
    WITH CHECK (current_setting('request.jwt.claim.role', true) = 'trudnikapp');

-- ============================================
-- 4. receipts — политика receipts_update
-- ============================================
DROP POLICY IF EXISTS "receipts_update" ON receipts;
CREATE POLICY "receipts_update" ON receipts
    FOR UPDATE
    TO trudnikapp
    USING (current_setting('request.jwt.claim.role', true) = 'trudnikapp')
    WITH CHECK (current_setting('request.jwt.claim.role', true) = 'trudnikapp');

COMMIT;

-- ============================================================================
-- ПРОВЕРКА:
--   SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual
--   FROM pg_policies
--   WHERE tablename IN ('skills', 'religions', 'receipts')
--   ORDER BY tablename, policyname;
--
-- ОЖИДАЕМЫЙ РЕЗУЛЬТАТ:
--   admin_skills      | roles={trudnikapp}
--   read_skills       | roles={public}        (без изменений)
--   admin_religions   | roles={trudnikapp}
--   read_religions    | roles={public}        (без изменений)
--   receipts_insert   | roles={trudnikapp}
--   receipts_update   | roles={trudnikapp}
-- ============================================================================
