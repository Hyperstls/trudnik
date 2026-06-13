-- ============================================================
-- Миграция 035: Исправление RLS-политики для статуса cancelled
-- ============================================================
-- Проблема: миграция 032 упростила статусы до ('open','completed','cancelled'),
-- но RLS-политика "Jobs are viewable by everyone" всё ещё содержит
-- старые статусы ('open','in_progress','active','completed').
-- Задания со статусом 'cancelled' не видны никому, кроме владельца и админа.

BEGIN;

-- 1. Удаляем старую политику
DROP POLICY IF EXISTS "Jobs are viewable by everyone" ON jobs;

-- 2. Создаём новую с актуальным списком статусов
CREATE POLICY "Jobs are viewable by everyone" ON jobs
    FOR SELECT USING (
        status IN ('open', 'completed', 'cancelled')
        OR ((SELECT auth.uid()) = employer_id)
        OR (EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'admin'
        ))
    );

COMMIT;
