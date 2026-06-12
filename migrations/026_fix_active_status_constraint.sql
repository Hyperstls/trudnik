-- Миграция 026: Исправление CHECK constraint для status в таблице jobs
-- Проблема: миграция 022 убрала 'active' из допустимых статусов,
-- но код использует статус 'active' (автопереход in_progress → active).
-- Ошибка: 23514 (CHECK constraint violation) при создании задания со статусом 'active'.
-- Решение: добавить 'active' обратно в список допустимых статусов.
-- Условия перехода в active регулируются в коде приложения
-- (_auto_transition_in_progress_to_active): date_time <= NOW() и статус = in_progress.

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;

ALTER TABLE jobs ADD CONSTRAINT jobs_status_check
    CHECK (status IN ('draft', 'open', 'in_progress', 'active', 'completed', 'cancelled', 'paid', 'expired'));
