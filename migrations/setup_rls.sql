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

-- ============================================
-- Дополнительно: настройка RLS для таблицы applications
-- ============================================

ALTER TABLE applications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can insert applications" ON applications;
DROP POLICY IF EXISTS "Users can read their own applications" ON applications;
DROP POLICY IF EXISTS "Employers can read applications for their jobs" ON applications;

-- Работники могут вставлять отклики (с указанием своего worker_id)
CREATE POLICY "Users can insert applications"
    ON applications
    FOR INSERT
    WITH CHECK (
        auth.uid() = worker_id
    );

-- Пользователи могут читать свои отклики
CREATE POLICY "Users can read their own applications"
    ON applications
    FOR SELECT
    USING (
        auth.uid() = worker_id
    );

-- Работодатели могут читать отклики на свои задания
CREATE POLICY "Employers can read applications for their jobs"
    ON applications
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = applications.job_id
            AND jobs.employer_id = auth.uid()
        )
    );

-- ============================================
-- Дополнительно: настройка RLS для таблицы shifts
-- ============================================

ALTER TABLE shifts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Workers can insert shifts" ON shifts;
DROP POLICY IF EXISTS "Users can read their own shifts" ON shifts;

-- Работодатель может создавать смену при принятии отклика
CREATE POLICY "Employers can insert shifts"
    ON shifts
    FOR INSERT
    WITH CHECK (
        auth.uid() = employer_id
    );

-- Пользователи могут читать свои смены
CREATE POLICY "Users can read their own shifts"
    ON shifts
    FOR SELECT
    USING (
        auth.uid() = worker_id OR auth.uid() = employer_id
    );

-- ============================================
-- Дополнительно: настройка RLS для таблицы ratings
-- ============================================

ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can insert ratings" ON ratings;
DROP POLICY IF EXISTS "Users can read ratings" ON ratings;

-- Пользователи могут вставлять оценки
CREATE POLICY "Users can insert ratings"
    ON ratings
    FOR INSERT
    WITH CHECK (
        auth.uid() = rater_user_id
    );

-- Все авторизованные пользователи могут читать оценки
CREATE POLICY "Users can read ratings"
    ON ratings
    FOR SELECT
    USING (
        true
    );

-- ============================================
-- Дополнительно: настройка RLS для таблицы notifications
-- ============================================

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read their own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can insert notifications" ON notifications;

-- Пользователи могут читать свои уведомления
CREATE POLICY "Users can read their own notifications"
    ON notifications
    FOR SELECT
    USING (
        auth.uid() = user_id
    );

-- Система может вставлять уведомления (через service role key)
CREATE POLICY "Service can insert notifications"
    ON notifications
    FOR INSERT
    WITH CHECK (
        true
    );
