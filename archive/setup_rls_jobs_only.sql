-- ============================================
-- Настройка Row Level Security (RLS) для таблицы jobs
-- ============================================

-- 1. Включить RLS (если ещё не включён)
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- 2. Удалить старые политики, если есть
DROP POLICY IF EXISTS "Employers can insert jobs" ON jobs;
DROP POLICY IF EXISTS "Users can read jobs" ON jobs;
DROP POLICY IF EXISTS "Employers can update their own jobs" ON jobs;
DROP POLICY IF EXISTS "Employers can delete their own jobs" ON jobs;

-- 3. Создать политики
-- 3.1. Работодатели могут вставлять задания (с указанием своего employer_id)
CREATE POLICY "Employers can insert jobs"
    ON jobs
    FOR INSERT
    WITH CHECK (
        auth.uid() = employer_id
    );

-- 3.2. Все авторизованные пользователи могут читать открытые задания
CREATE POLICY "Users can read jobs"
    ON jobs
    FOR SELECT
    USING (
        status = 'open' OR
        status = 'in_progress' OR
        status = 'active' OR
        status = 'payment_pending' OR
        status = 'paid'
    );

-- 3.3. Работодатель может обновлять свои задания
CREATE POLICY "Employers can update their own jobs"
    ON jobs
    FOR UPDATE
    USING (
        auth.uid() = employer_id
    )
    WITH CHECK (
        auth.uid() = employer_id
    );

-- 3.4. Работодатель может удалять свои задания
CREATE POLICY "Employers can delete their own jobs"
    ON jobs
    FOR DELETE
    USING (
        auth.uid() = employer_id
    );
