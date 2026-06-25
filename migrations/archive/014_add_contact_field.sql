-- Добавление поля contact в profiles для трудников
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS contact TEXT;
