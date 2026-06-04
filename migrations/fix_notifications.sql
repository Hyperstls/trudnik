-- Исправление таблицы notifications - добавление столбца is_read
-- Выполнить на Supabase Dashboard → SQL Editor только один раз

-- Добавить столбец is_read если он не существует
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'notifications' AND column_name = 'is_read'
    ) THEN
        ALTER TABLE notifications ADD COLUMN is_read BOOLEAN DEFAULT FALSE;
        CREATE INDEX idx_notifications_read ON notifications(is_read);
        RAISE NOTICE 'Столбец is_read успешно добавлен в таблицу notifications';
    ELSE
        RAISE NOTICE 'Столбец is_read уже существует в таблице notifications';
    END IF;
END $$;
