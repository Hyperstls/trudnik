-- Обновление таблицы jobs для жизненного цикла заданий
-- Выполнить на Supabase Dashboard → SQL Editor

-- 1. Добавить поле max_workers (максимальное количество работников)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS max_workers INTEGER DEFAULT 1 CHECK (max_workers >= 1);

-- 2. Добавить поле current_workers (текущее количество принятых работников)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_workers INTEGER DEFAULT 0 CHECK (current_workers >= 0 AND current_workers <= max_workers);

-- 3. Создать индексы для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_employer_id ON jobs(employer_id);
CREATE INDEX IF NOT EXISTS idx_jobs_current_workers ON jobs(current_workers);
CREATE INDEX IF NOT EXISTS idx_jobs_status_and_workers ON jobs(status, current_workers, max_workers);

-- 4. Добавить ограничение текущий workers <= max_workers
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_current_workers_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_current_workers_check 
    CHECK (current_workers >= 0 AND current_workers <= max_workers);

-- 5. Обновить существующие задания
UPDATE jobs SET max_workers = 1 WHERE max_workers IS NULL;
UPDATE jobs SET current_workers = 0 WHERE current_workers IS NULL;

-- ============================================
-- 6. Таблица ratings (оценки работников и работодателей)
-- ============================================
CREATE TABLE IF NOT EXISTS ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rated_user_id UUID REFERENCES auth.users(id) NOT NULL,
    rater_user_id UUID REFERENCES auth.users(id) NOT NULL,
    rating_type VARCHAR(20) NOT NULL CHECK (rating_type IN ('worker', 'employer')),
    target_type VARCHAR(20) NOT NULL CHECK (target_type IN ('worker', 'employer')),
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    shift_id UUID REFERENCES shifts(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(rated_user_id, rater_user_id, shift_id)
);

CREATE INDEX IF NOT EXISTS idx_ratings_rated_user ON ratings(rated_user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_rater_user ON ratings(rater_user_id);

-- ============================================
-- 7. Таблица notifications (уведомления)
-- ============================================
-- Создать таблицу только если она не существует
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    job_id UUID REFERENCES jobs(id),
    shift_id UUID REFERENCES shifts(id),
    application_id UUID REFERENCES applications(id),
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
