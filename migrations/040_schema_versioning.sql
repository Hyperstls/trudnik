-- ============================================================
-- 040: Schema Versioning
-- Таблица schema_migrations для отслеживания применённых миграций
-- ============================================================

-- Создание таблицы версионирования
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ DEFAULT NOW(),
    description TEXT
);

-- RLS: включаем для таблицы
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

-- Политика: только admin (service_role) может читать и писать
-- Для service_role RLS не применяется, поэтому отдельная политика для admin-роли приложения
DO $$ BEGIN
    DROP POLICY IF EXISTS "Admin can read schema_migrations" ON public.schema_migrations;
    CREATE POLICY "Admin can read schema_migrations" ON public.schema_migrations
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM profiles
                WHERE profiles.id = (SELECT auth.uid())
                  AND profiles.role = 'admin'
            )
        );
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'schema_migrations policy: %', SQLERRM;
END $$;

-- Вставляем запись о самой этой миграции
INSERT INTO public.schema_migrations (version, description)
VALUES ('040', 'Schema versioning: таблица schema_migrations с RLS')
ON CONFLICT (version) DO NOTHING;
