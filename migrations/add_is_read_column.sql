-- Добавление столбца is_read в существующую таблицу notifications
-- Выполнить на Supabase Dashboard → SQL Editor

-- Попытаться добавить столбец (если уже есть - будет ошибка, но это нормально)
BEGIN;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE;
COMMIT;

-- Создать индекс для ускорения запросов
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
