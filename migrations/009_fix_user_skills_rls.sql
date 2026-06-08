-- Миграция: ограничение видимости user_skills только аутентифицированными пользователями
-- Дата: 2026-06-08
-- Причина: политика read_user_skills с USING (true) раскрывала связку пользователь-навыки неаутентифицированным

-- 1. Удаляем старую слишком открытую политику
DROP POLICY IF EXISTS "read_user_skills" ON user_skills;

-- 2. Создаём новую — только для аутентифицированных
CREATE POLICY "read_user_skills" ON user_skills
    FOR SELECT
    USING (auth.uid() IS NOT NULL);

-- Примечание: read_job_skills оставлена публичной (USING (true)), т.к. навыки вакансий — общедоступная информация
