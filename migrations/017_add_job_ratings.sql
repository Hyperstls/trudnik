-- ============================================================
-- Миграция 017: Рейтинги и отзывы для заданий
-- Добавляет job_id в таблицу ratings, меняет уникальность,
-- добавляет возможность обновления оценки
-- Выполнить в Supabase SQL Editor
-- ============================================================

-- 1. Добавить колонки job_id и updated_at
ALTER TABLE IF EXISTS public.ratings
    ADD COLUMN IF NOT EXISTS job_id UUID REFERENCES public.jobs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- 2. Обновить существующие записи: перенести shift_id → job_id через shifts
UPDATE public.ratings r
SET job_id = s.job_id
FROM public.shifts s
WHERE r.shift_id = s.id AND r.job_id IS NULL;

-- 3. Удалить старый UNIQUE-constraint (PostgreSQL требует удаления через DROP)
ALTER TABLE IF EXISTS public.ratings DROP CONSTRAINT IF EXISTS ratings_rated_user_id_rater_user_id_shift_id_key;

-- 4. Добавить новый UNIQUE: один пользователь — одна оценка на задание
-- (позволяет UPDATE через ON CONFLICT)
ALTER TABLE IF EXISTS public.ratings
    ADD CONSTRAINT ratings_rater_job_unique UNIQUE (rater_user_id, job_id);

-- 5. Индекс для быстрого поиска оценок по заданию
CREATE INDEX IF NOT EXISTS idx_ratings_job ON public.ratings(job_id);

-- 6. Обновить RLS-политики для ratings
ALTER TABLE public.ratings ENABLE ROW LEVEL SECURITY;

-- Все могут читать оценки
DROP POLICY IF EXISTS "Anyone can read ratings" ON public.ratings;
CREATE POLICY "Anyone can read ratings" ON public.ratings
    FOR SELECT USING (true);

-- Авторизованные пользователи могут вставлять/обновлять свои оценки
DROP POLICY IF EXISTS "Users can upsert own ratings" ON public.ratings;
CREATE POLICY "Users can upsert own ratings" ON public.ratings
    FOR INSERT WITH CHECK (auth.uid() = rater_user_id);

CREATE POLICY "Users can update own ratings" ON public.ratings
    FOR UPDATE USING (auth.uid() = rater_user_id)
    WITH CHECK (auth.uid() = rater_user_id);

-- Админ может управлять всеми оценками
DROP POLICY IF EXISTS "Admin can manage ratings" ON public.ratings;
CREATE POLICY "Admin can manage ratings" ON public.ratings
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );
