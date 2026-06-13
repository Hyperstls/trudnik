-- Миграция 024: Исправление RLS-политик для jobs и applications
-- После сверки кода с реальной БД Supabase

-- 1. Исправить политику jobs SELECT: анонимы видят только open задания
DROP POLICY IF EXISTS "Jobs are viewable by everyone" ON jobs;

CREATE POLICY "Jobs are viewable by everyone" ON jobs
    FOR SELECT
    USING (
        status IN ('open', 'in_progress', 'active')
        OR (auth.uid() = employer_id)
        OR (EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'))
    );

-- 2. Исправить политику applications INSERT: только сам трудник может откликнуться
DROP POLICY IF EXISTS "Workers can insert applications" ON applications;

CREATE POLICY "Workers can insert applications" ON applications
    FOR INSERT
    WITH CHECK (
        auth.uid() = worker_id
        AND auth.uid() IS NOT NULL
    );

-- 3. Удалить устаревшие колонки старой модели монетизации
ALTER TABLE applications DROP COLUMN IF EXISTS contact_paid;
ALTER TABLE applications DROP COLUMN IF EXISTS contact_payment_id;
