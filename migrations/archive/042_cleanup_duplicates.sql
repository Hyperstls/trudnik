-- ============================================================
-- 042: Чистка дубликатов и мёртвых таблиц
-- - Проверка дубликатов колонок (notifications.read/is_read, profiles.religion/religion_id)
-- - Пометка мёртвых таблиц как DEPRECATED
-- Все операции идемпотентны
-- ============================================================

-- ═══════════════════════════════════════════════════════════════
-- 1. Дубликаты колонок: notifications.read vs is_read
-- ═══════════════════════════════════════════════════════════════
-- В коде используется is_read (Boolean), read — устаревший синоним.

DO $$
DECLARE
    has_read boolean;
    has_is_read boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notifications' AND column_name = 'read'
    ) INTO has_read;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notifications' AND column_name = 'is_read'
    ) INTO has_is_read;

    -- Если есть обе колонки, синхронизируем данные перед удалением
    IF has_read AND has_is_read THEN
        -- Копируем данные из read в is_read (где is_read IS NULL)
        UPDATE notifications
        SET is_read = read::boolean
        WHERE is_read IS NULL AND read IS NOT NULL;

        RAISE NOTICE 'notifications: синхронизированы read → is_read';

        -- Удаляем устаревшую колонку read
        ALTER TABLE public.notifications DROP COLUMN IF EXISTS read;
        RAISE NOTICE 'notifications: колонка read удалена (оставлена is_read)';
    ELSIF has_read AND NOT has_is_read THEN
        -- Только read — переименовываем в is_read
        ALTER TABLE public.notifications RENAME COLUMN read TO is_read;
        RAISE NOTICE 'notifications: колонка read переименована в is_read';
    ELSE
        RAISE NOTICE 'notifications: дубликатов нет (только is_read)';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'notifications cleanup: %', SQLERRM;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- 2. Дубликаты колонок: profiles.religion vs religion_id
-- ═══════════════════════════════════════════════════════════════
-- В коде используется preferred_religion (UUID → religions.id).
-- Колонка religion (text) — устаревшая.

DO $$
DECLARE
    has_religion_text boolean;
    has_religion_id boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'profiles' AND column_name = 'religion'
    ) INTO has_religion_text;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'profiles' AND column_name = 'religion_id'
    ) INTO has_religion_id;

    IF has_religion_text AND has_religion_id THEN
        RAISE NOTICE 'profiles: обе колонки (religion TEXT и religion_id UUID) существуют. religion_id — каноническая.';
        -- Не удаляем religion (текстовую) автоматически — может использоваться в шаблонах.
        -- Помечаем комментарием
        COMMENT ON COLUMN public.profiles.religion IS 'DEPRECATED: используйте religion_id (UUID → religions.id)';
    ELSIF has_religion_text THEN
        RAISE NOTICE 'profiles: только religion (TEXT). Рекомендуется миграция на religion_id (UUID).';
    ELSE
        RAISE NOTICE 'profiles: дубликатов нет';
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'profiles cleanup: %', SQLERRM;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- 3. Пометка мёртвых таблиц как DEPRECATED
-- ═══════════════════════════════════════════════════════════════

-- shifts — заменены на application-based чат (см. 027_drop_shifts_migrate_chat.sql)
DO $$ BEGIN
    COMMENT ON TABLE public.shifts IS 'DEPRECATED: заменены на application-based чат (messages.application_id). Миграция 027.';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

-- spatial_ref_sys — системная таблица PostGIS, не используется приложением
DO $$ BEGIN
    COMMENT ON TABLE public.spatial_ref_sys IS 'DEPRECATED: системная таблица PostGIS, не используется приложением.';
EXCEPTION WHEN OTHERS THEN NULL; END $$;

-- ═══════════════════════════════════════════════════════════════
-- 4. Идемпотентная вставка в schema_migrations (если таблица создана)
-- ═══════════════════════════════════════════════════════════════

DO $$ BEGIN
    INSERT INTO public.schema_migrations (version, description)
    VALUES ('041', 'FK messages: sender_id → profiles.id, application_id → applications.id ON DELETE CASCADE')
    ON CONFLICT (version) DO NOTHING;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'schema_migrations table not found — skipping insert for 041';
END $$;

DO $$ BEGIN
    INSERT INTO public.schema_migrations (version, description)
    VALUES ('042', 'Cleanup: дубликаты колонок, пометка мёртвых таблиц')
    ON CONFLICT (version) DO NOTHING;
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'schema_migrations table not found — skipping insert for 042';
END $$;
