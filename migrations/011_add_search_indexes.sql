-- Полнотекстовый поиск: generated tsvector колонки + GIN индексы
-- Выполнить в Supabase SQL Editor

-- ============================================
-- 1. Таблица jobs: поиск по названию, описанию, адресу
-- ============================================
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('russian', coalesce(organization_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(object_description, '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(detailed_description, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(work_type, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(address, '')), 'D')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs USING GIN(search_vector);

-- ============================================
-- 2. Таблица profiles: поиск трудников по имени, навыкам, био, городу
-- ============================================
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('russian', coalesce(full_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(skills, '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(bio, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(city, '')), 'D')
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_profiles_search ON profiles USING GIN(search_vector);
