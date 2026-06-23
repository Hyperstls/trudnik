-- ============================================================================
-- Миграция 068: Исправление расхождений pgAdmin-дампа с миграциями
-- Файл: migrations/068_fix_pgadmin_gaps.sql
-- Дата: 2026-06-23
-- ============================================================================
--
-- НАЗНАЧЕНИЕ:
--   Точечные исправления расхождений, выявленных при сверке pgAdmin-дампа
--   с bootstrap-миграциями. Все операции идемпотентны (IF EXISTS/IF NOT EXISTS).
--
-- ЧТО ВКЛЮЧЕНО:
--   1. Добавление 'cancelled' в CHECK constraint applications.status
--   2. Создание RLS-политик для employer_details (SELECT, INSERT, UPDATE)
--   3. Создание RLS-политик для job_favorites (SELECT, INSERT, DELETE)
--   4. Создание RLS-политик для job_photos (SELECT, INSERT, DELETE через JOIN)
--   5. Удаление лишних индексов (idx_favorites_target_id, idx_favorites_type)
-- ============================================================================

-- ============================================
-- СЕКЦИЯ 1: Починить CHECK для applications.status
-- Проблема: RPC cancel_worker_atomic устанавливает status = 'cancelled',
-- но CHECK constraint не включает это значение.
-- Решение: удалить старый constraint и создать новый с 'cancelled'.
-- ============================================

ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_status_check;
ALTER TABLE applications ADD CONSTRAINT applications_status_check CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn', 'cancelled'));

-- ============================================
-- СЕКЦИЯ 2: Создать RLS-политики для employer_details
-- Проблема: в bootstrap-миграциях отсутствуют политики для employer_details,
-- хотя RLS на таблице включён. Пользователь должен видеть/менять только свои записи.
-- ============================================

-- Включаем RLS (идемпотентно, если уже включено — ничего не делает)
ALTER TABLE employer_details ENABLE ROW LEVEL SECURITY;

-- Удаляем старые политики, если существуют
DROP POLICY IF EXISTS employer_details_select_policy ON employer_details;
DROP POLICY IF EXISTS employer_details_insert_policy ON employer_details;
DROP POLICY IF EXISTS employer_details_update_policy ON employer_details;
DROP POLICY IF EXISTS employer_details_select ON employer_details;

-- SELECT: пользователь видит только свою запись
CREATE POLICY employer_details_select_policy
    ON employer_details
    FOR SELECT
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- INSERT: пользователь может создать запись только для себя
CREATE POLICY employer_details_insert_policy
    ON employer_details
    FOR INSERT
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- UPDATE: пользователь может обновлять только свою запись
CREATE POLICY employer_details_update_policy
    ON employer_details
    FOR UPDATE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id)
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- ============================================
-- СЕКЦИЯ 3: Создать RLS-политики для job_favorites
-- Проблема: в bootstrap-миграциях отсутствуют политики для job_favorites,
-- хотя RLS на таблице включён. По аналогии с favorites — доступ по user_id.
-- ============================================

-- Удаляем старые политики, если существуют
DROP POLICY IF EXISTS job_favorites_select_policy ON job_favorites;
DROP POLICY IF EXISTS job_favorites_insert_policy ON job_favorites;
DROP POLICY IF EXISTS job_favorites_delete_policy ON job_favorites;

-- SELECT: пользователь видит только свои избранные задания
CREATE POLICY job_favorites_select_policy
    ON job_favorites
    FOR SELECT
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- INSERT: пользователь может добавить в избранное только для себя
CREATE POLICY job_favorites_insert_policy
    ON job_favorites
    FOR INSERT
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- DELETE: пользователь может удалять только свои избранные
CREATE POLICY job_favorites_delete_policy
    ON job_favorites
    FOR DELETE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- ============================================
-- СЕКЦИЯ 4: Создать RLS-политики для job_photos
-- Проблема: в bootstrap-миграциях отсутствуют политики для job_photos,
-- хотя RLS на таблице включён.
-- Логика: пользователь видит/управляет фото только своих заданий
-- (через JOIN с jobs по job_id -> employer_id).
-- ============================================

-- Удаляем старые политики, если существуют
DROP POLICY IF EXISTS job_photos_select_policy ON job_photos;
DROP POLICY IF EXISTS job_photos_insert_policy ON job_photos;
DROP POLICY IF EXISTS job_photos_delete_policy ON job_photos;

-- SELECT: пользователь видит фото заданий, владельцем которых он является
CREATE POLICY job_photos_select_policy
    ON job_photos
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = job_photos.job_id
            AND jobs.employer_id = current_setting('request.jwt.claim.user_id', true)::uuid
        )
    );

-- INSERT: пользователь может добавить фото только к своему заданию
CREATE POLICY job_photos_insert_policy
    ON job_photos
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = job_photos.job_id
            AND jobs.employer_id = current_setting('request.jwt.claim.user_id', true)::uuid
        )
    );

-- DELETE: пользователь может удалять фото только своих заданий
CREATE POLICY job_photos_delete_policy
    ON job_photos
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = job_photos.job_id
            AND jobs.employer_id = current_setting('request.jwt.claim.user_id', true)::uuid
        )
    );

-- ============================================
-- СЕКЦИЯ 5: Удалить лишние индексы
-- Индексы idx_favorites_target_id и idx_favorites_type более не нужны
-- (не используются в запросах и не соответствуют текущей схеме).
-- ============================================

DROP INDEX IF EXISTS idx_favorites_target_id;
DROP INDEX IF EXISTS idx_favorites_type;

-- ============================================================================
-- ГОТОВО!
-- Все операции идемпотентны — скрипт можно запускать повторно без ошибок.
-- ============================================================================
