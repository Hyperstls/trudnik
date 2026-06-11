-- ============================================================
-- Миграция: включить RLS на public.spatial_ref_sys
-- Исправляет предупреждение Supabase Linter:
--   "Table public.spatial_ref_sys is public, but RLS has not been enabled."
-- Выполнить в Supabase SQL Editor
-- ============================================================
-- spatial_ref_sys — системная таблица PostGIS (справочник систем координат).
-- Данные read-only, PostGIS функции используют владельца(postgres),
-- который обходит RLS. Включение RLS + read-only политика
-- подавляет lint-предупреждение без изменения функциональности.

ALTER TABLE IF EXISTS public.spatial_ref_sys ENABLE ROW LEVEL SECURITY;

-- Read-only политика для аутентифицированных пользователей
-- (анонимные не имеют доступа к API)
DO $$ BEGIN
    DROP POLICY IF EXISTS "spatial_ref_sys_select" ON public.spatial_ref_sys;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "spatial_ref_sys_select"
        ON public.spatial_ref_sys
        FOR SELECT
        USING (true);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
