-- ============================================
-- Миграция 019: Добавление недостающих колонок в таблицу notifications
-- Проблема: 003_add_max_workers.sql использовал CREATE TABLE IF NOT EXISTS,
-- и если таблица уже существовала с минимальным набором колонок,
-- то title, job_id, shift_id, application_id отсутствуют в production.
-- ============================================

-- Добавляем колонки только если их нет
DO $$
BEGIN
    -- title
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'notifications' AND column_name = 'title') THEN
        ALTER TABLE notifications ADD COLUMN title TEXT;
    END IF;

    -- job_id
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'notifications' AND column_name = 'job_id') THEN
        ALTER TABLE notifications ADD COLUMN job_id UUID REFERENCES jobs(id);
    END IF;

    -- shift_id
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'notifications' AND column_name = 'shift_id') THEN
        ALTER TABLE notifications ADD COLUMN shift_id UUID REFERENCES shifts(id);
    END IF;

    -- application_id
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'notifications' AND column_name = 'application_id') THEN
        ALTER TABLE notifications ADD COLUMN application_id UUID REFERENCES applications(id);
    END IF;
END $$;
