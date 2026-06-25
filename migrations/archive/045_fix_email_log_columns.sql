-- Миграция 045: Добавление недостающих колонок в email_log
-- Исправление несоответствия схемы после ревью

BEGIN;

ALTER TABLE email_log ADD COLUMN IF NOT EXISTS to_email TEXT;
ALTER TABLE email_log ADD COLUMN IF NOT EXISTS subject TEXT;
ALTER TABLE email_log ADD COLUMN IF NOT EXISTS template_name VARCHAR(100);
ALTER TABLE email_log ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ;
ALTER TABLE email_log ADD COLUMN IF NOT EXISTS error_message TEXT;

COMMIT;
