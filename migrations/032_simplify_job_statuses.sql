-- Удалить старый constraint
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
-- Новый constraint с тремя статусами
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (status IN ('open', 'completed', 'cancelled'));
-- Перевести существующие in_progress и active в completed
UPDATE jobs SET status = 'completed' WHERE status IN ('in_progress', 'active');
