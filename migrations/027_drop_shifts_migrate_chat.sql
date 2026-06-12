-- ============================================================
-- Миграция 027: Удаление таблицы shifts, миграция чата на application_id
-- Дата: 2026-06-12
-- Контекст: P2 — новая модель без таблицы shifts.
--   Чат теперь привязан к application_id вместо shift_id.
-- ============================================================

-- 1. Добавить колонку application_id в messages (сначала без NOT NULL)
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS application_id UUID REFERENCES applications(id);

-- 2. Скопировать данные: shift_id → application_id через JOIN с applications
--    applications.shift_id = messages.shift_id → берём applications.id
UPDATE messages m
SET application_id = a.id
FROM applications a
WHERE a.shift_id = m.shift_id
  AND m.shift_id IS NOT NULL;

-- 3. Удалить колонку shift_id из messages
ALTER TABLE messages
DROP COLUMN IF EXISTS shift_id;

-- 4. Удалить колонку shift_id из applications
ALTER TABLE applications
DROP COLUMN IF EXISTS shift_id;

-- 5. Удалить таблицу shifts (после миграции данных!)
DROP TABLE IF EXISTS shifts CASCADE;

-- 6. Индекс на messages.application_id для быстрых JOIN и фильтрации
CREATE INDEX IF NOT EXISTS idx_messages_application_id
ON messages(application_id);

-- 7. CHECK constraint на jobs.status — только допустимые статусы новой модели
--    (исключаем payment_pending, paid, disputed)
ALTER TABLE jobs
DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE jobs
ADD CONSTRAINT jobs_status_check
CHECK (status IN ('open', 'in_progress', 'active', 'completed', 'cancelled'));

-- 8. Удалить устаревшие внешние ключи и индексы (если остались после CASCADE)
--    CASCADE из DROP TABLE shifts уже должен был удалить FK, но на всякий случай:
ALTER TABLE messages
DROP CONSTRAINT IF EXISTS messages_shift_id_fkey;

-- 9. Очистить устаревшие статусы в jobs (на случай, если в БД остались строки со старыми статусами)
UPDATE jobs SET status = 'completed'
WHERE status IN ('payment_pending', 'paid', 'disputed');

UPDATE jobs SET status = 'active'
WHERE status = 'in_progress' AND date_time <= now();
