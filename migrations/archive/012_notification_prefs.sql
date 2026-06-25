-- Расширение системы уведомлений
-- Выполнить в Supabase SQL Editor

-- 1. Добавить поле data (JSON) в notifications для хранения связанных ID
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS data JSONB DEFAULT '{}'::jsonb;

-- 2. Добавить поле notification_prefs (JSON) в profiles для настроек уведомлений
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{}'::jsonb;
