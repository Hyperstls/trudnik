-- Миграция 063: Добавление колонки job_id в таблицу notifications
-- Дата: 2026-06-22
-- Описание: Добавляет прямую колонку job_id для быстрых JOIN-запросов
--   и удаления orphaned-уведомлений без парсинга текста/JSON.
-- Обратная совместимость: миграция идемпотентна (IF NOT EXISTS).

-- 1. Добавляем колонку job_id с внешним ключом на jobs
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS job_id UUID REFERENCES jobs(id) ON DELETE SET NULL;

-- 2. Создаём индекс для быстрых запросов по job_id
CREATE INDEX IF NOT EXISTS idx_notifications_job_id ON notifications(job_id);

-- 3. Переносим данные из JSON-поля data в прямую колонку
--    (для уведомлений, созданных до миграции)
UPDATE notifications
SET job_id = (data->>'job_id')::uuid
WHERE data->>'job_id' IS NOT NULL
  AND job_id IS NULL
  AND (data->>'job_id') ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

-- 4. Создаём индекс для application_id (уже может существовать)
CREATE INDEX IF NOT EXISTS idx_notifications_application_id ON notifications(application_id);
