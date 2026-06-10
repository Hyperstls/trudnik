-- ============================================================
-- Миграция: исправление предупреждений Supabase Linter
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- 1. spatial_ref_sys — системная таблица PostGIS, нельзя менять (пропускаем)

-- 2. Mutable search_path в функциях
ALTER FUNCTION public.nearby_jobs SET search_path = '';
ALTER FUNCTION public.jobs_search_update SET search_path = '';
ALTER FUNCTION public.profiles_search_update SET search_path = '';
ALTER FUNCTION public.handle_new_user SET search_path = '';

-- 3. Storage buckets: убрать широкий SELECT
-- avatars и jobs ДОЛЖНЫ быть публичными (фото профилей и заданий)
-- verification-docs: только аутентифицированные пользователи
DROP POLICY IF EXISTS "Public read 1oj01fe_0" ON storage.objects;
DROP POLICY IF EXISTS "Public read avatars" ON storage.objects;
DROP POLICY IF EXISTS "Public read jobs photos" ON storage.objects;
DROP POLICY IF EXISTS "Public read verification docs" ON storage.objects;
CREATE POLICY "Public read avatars" ON storage.objects
    FOR SELECT USING (bucket_id = 'avatars');
CREATE POLICY "Public read jobs photos" ON storage.objects
    FOR SELECT USING (bucket_id = 'jobs');
CREATE POLICY "Auth read verification docs" ON storage.objects
    FOR SELECT USING (bucket_id = 'verification-docs' AND auth.role() = 'authenticated');

-- 4. Запретить выполнение SECURITY DEFINER функций (повторно, с проверкой)
DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION public.execute_sql(text) FROM anon, authenticated;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
DO $$
BEGIN
    REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon, authenticated;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- 5. RLS политики для таблиц без политик
-- push_subscriptions
DROP POLICY IF EXISTS "Users can view own push subscriptions" ON public.push_subscriptions;
CREATE POLICY "Users can view own push subscriptions" ON public.push_subscriptions
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own push subscriptions" ON public.push_subscriptions
    FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own push subscriptions" ON public.push_subscriptions
    FOR DELETE USING (auth.uid() = user_id);

-- ratings
DROP POLICY IF EXISTS "Users can view ratings" ON public.ratings;
CREATE POLICY "Users can view ratings" ON public.ratings
    FOR SELECT USING (true);
CREATE POLICY "Users can insert own ratings" ON public.ratings
    FOR INSERT WITH CHECK (auth.uid() = rater_user_id);
CREATE POLICY "Users can update own ratings" ON public.ratings
    FOR UPDATE USING (auth.uid() = rater_user_id);
