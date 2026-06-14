-- ============================================================
-- 041: FK для messages — sender_id → profiles.user_id ON DELETE CASCADE
-- Проверка существования messages.application_id → applications.id ON DELETE CASCADE
-- Все операции идемпотентны (DO $$ блоки)
-- ============================================================

-- 1. FK: messages.sender_id → profiles.id ON DELETE CASCADE
DO $$
DECLARE
    fk_exists boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = 'messages'
          AND ccu.table_name = 'profiles'
          AND ccu.column_name = 'id'
    ) INTO fk_exists;

    IF NOT fk_exists THEN
        -- Убедимся, что нет битых ссылок
        DELETE FROM messages
        WHERE sender_id IS NOT NULL
          AND sender_id NOT IN (SELECT id FROM profiles);

        ALTER TABLE public.messages
            ADD CONSTRAINT fk_messages_sender_id
            FOREIGN KEY (sender_id)
            REFERENCES public.profiles(id)
            ON DELETE CASCADE;

        RAISE NOTICE 'FK messages.sender_id → profiles.id created';
    ELSE
        RAISE NOTICE 'FK messages.sender_id → profiles.id already exists';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'FK messages.sender_id: %', SQLERRM;
END $$;

-- 2. FK: messages.application_id → applications.id ON DELETE CASCADE
DO $$
DECLARE
    fk_exists boolean;
    col_exists boolean;
BEGIN
    -- Проверим, есть ли колонка application_id
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'messages'
          AND column_name = 'application_id'
    ) INTO col_exists;

    IF col_exists THEN
        SELECT EXISTS (
            SELECT 1 FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = 'messages'
              AND ccu.table_name = 'applications'
              AND ccu.column_name = 'id'
        ) INTO fk_exists;

        IF NOT fk_exists THEN
            -- Убедимся, что нет битых ссылок
            DELETE FROM messages
            WHERE application_id IS NOT NULL
              AND application_id NOT IN (SELECT id FROM applications);

            ALTER TABLE public.messages
                ADD CONSTRAINT fk_messages_application_id
                FOREIGN KEY (application_id)
                REFERENCES public.applications(id)
                ON DELETE CASCADE;

            RAISE NOTICE 'FK messages.application_id → applications.id created';
        ELSE
            RAISE NOTICE 'FK messages.application_id → applications.id already exists';
        END IF;
    ELSE
        RAISE NOTICE 'Column messages.application_id does not exist — skipped';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'FK messages.application_id: %', SQLERRM;
END $$;
