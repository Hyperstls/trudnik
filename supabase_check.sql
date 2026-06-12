# SQL-запросы для сверки кода с БД Supabase
# Выполните в Supabase SQL Editor и пришлите результат

-- 1. Все таблицы в схеме public
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' ORDER BY table_name;

-- 2. Колонки jobs + applications
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_schema = 'public' AND table_name IN ('jobs', 'applications')
ORDER BY table_name, ordinal_position;

-- 3. RLS политики
SELECT tablename, policyname, cmd, qual 
FROM pg_policies WHERE schemaname = 'public'
ORDER BY tablename, policyname;

-- 4. Тарифы и настройки
SELECT * FROM tariff_settings;
SELECT * FROM monetization_settings;

-- 5. Тестовые пользователи
SELECT id, email FROM auth.users WHERE email LIKE '%test.ru';
