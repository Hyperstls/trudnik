-- Миграция 036: Добавление поддержки избранного работодателей
BEGIN;

-- 1. Добавить колонку favorite_type
ALTER TABLE public.favorites
    ADD COLUMN IF NOT EXISTS favorite_type TEXT NOT NULL DEFAULT 'worker';

-- 2. Добавить CHECK-constraint
ALTER TABLE public.favorites
    ADD CONSTRAINT favorites_type_check CHECK (favorite_type IN ('worker', 'employer'));

-- 3. Обновить первичный ключ с учётом favorite_type
ALTER TABLE public.favorites DROP CONSTRAINT IF EXISTS favorites_pkey;
ALTER TABLE public.favorites
    ADD CONSTRAINT favorites_pkey PRIMARY KEY (user_id, target_id, favorite_type);

-- 4. Индекс для быстрого поиска по типу
CREATE INDEX IF NOT EXISTS idx_favorites_type ON public.favorites(favorite_type);

COMMIT;
