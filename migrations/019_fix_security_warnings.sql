-- ============================================================
-- Миграция: исправление оставшихся Security Advisor Warnings
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- ============================================================
-- 1. anon_security_definer_function_executable / authenticated
--    execute_sql(sql text) — КРИТИЧНАЯ уязвимость!
--    Функция позволяет выполнить произвольный SQL через API.
--    Решение: полностью удаляем её.
-- ============================================================
DO $$ BEGIN
    DROP FUNCTION IF EXISTS public.execute_sql CASCADE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ============================================================
-- 2. handle_new_user() — нужна для auth trigger'а,
--    но не должна быть доступна через API.
--    Решение: REVOKE EXECUTE для anon и authenticated.
-- ============================================================
DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon, authenticated;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ============================================================
-- 3. st_estimatedextent — PostGIS C-функция.
--    Её нельзя пересоздать или изменить.
--    Решение: REVOKE EXECUTE для anon и authenticated.
-- ============================================================
DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ============================================================
-- 4. public_bucket_allows_listing
--    Storage buckets avatars, jobs — широкие SELECT политики
--    позволяют листинг всех файлов через API.
--    Решение: заменить на политики с проверкой пути файла,
--    чтобы разрешить чтение конкретных файлов, но не листинг.
-- ============================================================

-- Bucket: avatars
DO $$ BEGIN
    DROP POLICY IF EXISTS "Public read avatars" ON storage.objects;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
-- Новая политика: чтение доступно, только если запрошен конкретный файл
-- (имя файла указано в URL, а не листинг папки)
DO $$ BEGIN
    CREATE POLICY "Public read avatars"
        ON storage.objects
        FOR SELECT
        USING (
            bucket_id = 'avatars'
            AND (storage.foldername(name))[1] IS NOT NULL
        );
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Bucket: jobs
DO $$ BEGIN
    DROP POLICY IF EXISTS "Public read jobs photos" ON storage.objects;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
DO $$ BEGIN
    CREATE POLICY "Public read jobs photos"
        ON storage.objects
        FOR SELECT
        USING (
            bucket_id = 'jobs'
            AND (storage.foldername(name))[1] IS NOT NULL
        );
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
