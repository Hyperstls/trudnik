-- Фикс: GRANT service_role TO trudnikapp
-- Выполнить от имени postgres (суперпользователь) на БД trudnik
-- Дата: 2026-06-24
-- Причина: ошибка "permission denied to set role service_role" в логах trudnik-db

GRANT anon, authenticated, service_role TO trudnikapp;
