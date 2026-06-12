-- ============================================================================
-- Миграция 028: Комплексная синхронизация БД с кодом
-- Дата: 2026-06-12
-- Контекст: Сверка кода с реальной БД Supabase выявила критические расхождения.
--   Эта миграция — единый скрипт для их устранения. Выполнять в Supabase SQL Editor.
--   Идемпотентна: все операции с IF EXISTS / IF NOT EXISTS.
--   ВАЖНО: Безопасна для повторного запуска — все обращения к reviews/hires
--          обёрнуты в проверки существования таблиц.
-- ============================================================================

-- ============================================================================
-- ШАГ 1: Сначала DROP POLICY — снять RLS-политики, ссылающиеся на shift_id
-- ПОЧЕМУ ПЕРВЫМ: PostgreSQL не даст дропнуть колонку shift_id, пока на неё
--   ссылаются RLS-политики в USING/WITH CHECK выражениях.
--   Ошибка: "cannot drop column shift_id because other objects depend on it"
-- ============================================================================

-- 1a. SELECT-политика messages: ссылается на shift_id в USING
DROP POLICY IF EXISTS "Shift participants can view messages" ON messages;

-- 1b. INSERT-политика messages: ссылается на shift_id (на всякий случай, хоть и смотрит на sender_id)
DROP POLICY IF EXISTS "Shift participants can insert messages" ON messages;

-- 1c. Если уже существует новая политика от предыдущего неудачного запуска — тоже дропнуть
DROP POLICY IF EXISTS "Application participants can view messages" ON messages;
DROP POLICY IF EXISTS "Application participants can insert messages" ON messages;

-- ============================================================================
-- ШАГ 2: Разорвать все FK на таблицу shifts (блокируют DROP TABLE shifts)
--   ВАЖНО: Обёрнуто в DO-блок с проверкой существования таблиц,
--   т.к. reviews и hires могли быть удалены при предыдущем частичном запуске.
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ratings') THEN
        ALTER TABLE ratings DROP CONSTRAINT IF EXISTS ratings_shift_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'reviews') THEN
        ALTER TABLE reviews DROP CONSTRAINT IF EXISTS reviews_shift_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'hires') THEN
        ALTER TABLE hires DROP CONSTRAINT IF EXISTS hires_shift_id_fkey;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'messages') THEN
        ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_shift_id_fkey;
    END IF;
END $$;

-- ============================================================================
-- ШАГ 3: Дропнуть индексы на shift_id (зависят от колонки)
-- ============================================================================
DROP INDEX IF EXISTS idx_ratings_shift_id;
DROP INDEX IF EXISTS idx_reviews_shift_id;
DROP INDEX IF EXISTS idx_hires_shift_id;
DROP INDEX IF EXISTS idx_messages_shift_id;
DROP INDEX IF EXISTS idx_shifts_employer_id;
DROP INDEX IF EXISTS idx_shifts_job_id;
DROP INDEX IF EXISTS idx_shifts_worker_id;

-- ============================================================================
-- ШАГ 4: Добавить application_id в messages (новая модель: чат привязан к заявке)
-- ============================================================================
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS application_id UUID REFERENCES applications(id);

-- Попытка миграции исторических данных: если в applications есть shift_id,
-- смапить messages.shift_id → applications.id и проставить application_id.
-- Если колонки shift_id в applications нет — исторические сообщения теряют привязку.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'applications' AND column_name = 'shift_id'
    ) THEN
        UPDATE messages m
        SET application_id = a.id
        FROM applications a
        WHERE a.shift_id = m.shift_id
          AND m.shift_id IS NOT NULL;
    END IF;
END $$;

-- ============================================================================
-- ШАГ 5: Дропнуть колонку shift_id из всех зависимых таблиц
--   (RLS-политики уже сняты на ШАГЕ 1, FK — на ШАГЕ 2, индексы — на ШАГЕ 3)
--   ВАЖНО: Обёрнуто в DO-блок с проверкой существования таблиц,
--   т.к. reviews и hires могли быть удалены при предыдущем частичном запуске.
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'messages') THEN
        ALTER TABLE messages DROP COLUMN IF EXISTS shift_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ratings') THEN
        ALTER TABLE ratings DROP COLUMN IF EXISTS shift_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'reviews') THEN
        ALTER TABLE reviews DROP COLUMN IF EXISTS shift_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'hires') THEN
        ALTER TABLE hires DROP COLUMN IF EXISTS shift_id;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'applications') THEN
        ALTER TABLE applications DROP COLUMN IF EXISTS shift_id;
    END IF;
END $$;

-- ============================================================================
-- ШАГ 6: Дропнуть таблицу shifts (CASCADE удалит оставшиеся FK и политики RLS)
-- ============================================================================
DROP TABLE IF EXISTS shifts CASCADE;

-- ============================================================================
-- ШАГ 7: Обновить CHECK constraints — привести к реально используемым статусам
-- ============================================================================

-- 7a. jobs: open, in_progress, active, completed, cancelled
--     (draft, paid, expired — не используются в коде)
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('open', 'in_progress', 'active', 'completed', 'cancelled'));

-- 7b. applications: pending, accepted, rejected, withdrawn
--     (withdrawn нужен для отзыва отклика трудником)
ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_status_check;
ALTER TABLE applications ADD CONSTRAINT applications_status_check
    CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn'));

-- Перевести существующие строки со старыми статусами в актуальные
UPDATE jobs SET status = 'cancelled' WHERE status IN ('draft', 'expired');
UPDATE jobs SET status = 'completed' WHERE status IN ('paid');

-- ============================================================================
-- ШАГ 8: Создать НОВЫЕ RLS для messages — используют application_id вместо shift_id
--   ВАЖНО: DROP POLICY IF EXISTS перед CREATE для идемпотентности при повторе.
-- ============================================================================

-- 8a. SELECT: участники заявки (worker_id из applications, employer_id через jobs)
DROP POLICY IF EXISTS "Application participants can view messages" ON messages;
CREATE POLICY "Application participants can view messages" ON messages
    FOR SELECT USING (
        (SELECT auth.uid()) IN (
            SELECT worker_id FROM applications WHERE applications.id = messages.application_id
            UNION
            SELECT jobs.employer_id FROM applications
            JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.id = messages.application_id
        )
    );

-- 8b. INSERT: только сам отправитель может вставить своё сообщение
DROP POLICY IF EXISTS "Application participants can insert messages" ON messages;
CREATE POLICY "Application participants can insert messages" ON messages
    FOR INSERT WITH CHECK (
        (SELECT auth.uid()) = sender_id
    );

-- ============================================================================
-- ШАГ 9: Обновить RLS для jobs SELECT — показывать все актуальные статусы
-- ============================================================================
DROP POLICY IF EXISTS "Jobs are viewable by everyone" ON jobs;
DROP POLICY IF EXISTS "Users can read jobs" ON jobs;

CREATE POLICY "Jobs are viewable by everyone" ON jobs
    FOR SELECT USING (
        status IN ('open', 'in_progress', 'active', 'completed')
        OR ((SELECT auth.uid()) = employer_id)
        OR (EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'admin'
        ))
    );

-- ============================================================================
-- ШАГ 10: Создать новые индексы
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_messages_application_id ON messages(application_id);

-- ============================================================================
-- ШАГ 11: Дропнуть неиспользуемые таблицы (легаси)
-- ============================================================================
DROP TABLE IF EXISTS reviews CASCADE;  -- дублирует ratings
DROP TABLE IF EXISTS hires CASCADE;    -- не используется в коде

-- ============================================================================
-- ШАГ 12: Обновить RLS для applications — актуализировать политики
-- ============================================================================

-- Приводим к единому виду с (SELECT auth.uid()) для избежания auth_rls_initplan
DROP POLICY IF EXISTS "Users can read their own applications" ON applications;
DROP POLICY IF EXISTS "Users can view own applications" ON applications;

CREATE POLICY "Users can view own applications" ON applications
    FOR SELECT USING (
        (SELECT auth.uid()) = worker_id
        OR (SELECT auth.uid()) IN (
            SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id
        )
    );

DROP POLICY IF EXISTS "Employers can read applications for their jobs" ON applications;
DROP POLICY IF EXISTS "Employers can update applications" ON applications;

CREATE POLICY "Employers can update applications" ON applications
    FOR UPDATE USING (
        (SELECT auth.uid()) IN (
            SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id
        )
    );

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
