-- ============================================================
-- ФИНАЛЬНЫЙ ФИКС: рейтинг + оставшиеся SECURITY DEFINER
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- ============================================================
-- 1. multiple_permissive_policies: ratings
--   "Admin can manage ratings" (ALL) дублирует:
--     - "Users can insert own ratings" (INSERT)
--     - "Anyone can read ratings" (SELECT)
--     - "Users can update own ratings" (UPDATE)
--   Административные операции используют supabase_admin_request,
--   который обходит RLS — политика админа не нужна.
-- ============================================================
DROP POLICY IF EXISTS "Admin can manage ratings" ON public.ratings;

-- ============================================================
-- 2. st_estimatedextent — PostGIS C-функции
--   REVOKE EXECUTE может не работать без superuser.
--   Если FAIL — просто ignore warning.
-- ============================================================
DO $$ BEGIN
    REVOKE ALL ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated, public;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'st_estimatedextent(2 args): %', SQLERRM;
END $$;

DO $$ BEGIN
    REVOKE ALL ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated, public;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'st_estimatedextent(3 args): %', SQLERRM;
END $$;

DO $$ BEGIN
    REVOKE ALL ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated, public;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'st_estimatedextent(4 args): %', SQLERRM;
END $$;

-- ============================================================
-- ГОТОВО!
-- ============================================================
