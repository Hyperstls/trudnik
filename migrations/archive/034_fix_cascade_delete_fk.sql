-- ============================================================
-- Миграция 034: Исправление FK messages.application_id на CASCADE
-- Дата: 2026-06-13
-- Контекст: При удалении задания из таблицы jobs возникает ошибка FK:
--   messages ссылается на applications с ON DELETE NO ACTION.
--   Цепочка: jobs → applications (CASCADE ✅) → messages (NO ACTION ❌).
--
-- Решение: Заменить messages_application_id_fkey с NO ACTION на CASCADE.
--   После этого удаление jobs каскадно удалит applications,
--   а те — все связанные messages.
--
-- Примечание: notifications не имеет колонок job_id/application_id,
--   поэтому FK на них отсутствуют и не требуют исправления.
-- ============================================================

-- FK messages.application_id → applications.id
-- При удалении applications (каскадно от jobs)
-- messages блокирует удаление, т.к. FK стоит с NO ACTION.
ALTER TABLE messages
DROP CONSTRAINT IF EXISTS messages_application_id_fkey;

ALTER TABLE messages
ADD CONSTRAINT messages_application_id_fkey
FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE;

-- ============================================================
-- Проверочный запрос: показать текущий FK messages.application_id
-- с правилом удаления (должен показать CASCADE)
-- ============================================================
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name = 'messages'
  AND kcu.column_name = 'application_id'
ORDER BY tc.table_name, kcu.column_name;
