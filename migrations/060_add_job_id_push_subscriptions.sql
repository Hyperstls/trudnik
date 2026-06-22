-- Миграция 060: Добавление колонки job_id в push_subscriptions
-- Для контекстных push-уведомлений (привязка к конкретному заданию)
-- Дата: 2026-06-22

BEGIN;

-- 1. Добавляем колонку job_id (NULL по умолчанию — не все подписки контекстные)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'push_subscriptions' AND column_name = 'job_id'
    ) THEN
        ALTER TABLE push_subscriptions
        ADD COLUMN job_id uuid REFERENCES jobs(id) ON DELETE SET NULL;
    END IF;
END $$;

-- 2. Добавляем индекс для быстрого поиска подписок по заданию
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'push_subscriptions' AND indexname = 'idx_push_subscriptions_job_id'
    ) THEN
        CREATE INDEX idx_push_subscriptions_job_id ON push_subscriptions(job_id)
        WHERE job_id IS NOT NULL;
    END IF;
END $$;

COMMIT;
