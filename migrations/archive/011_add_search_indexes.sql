-- Полнотекстовый поиск: tsvector колонки + GIN индексы + триггеры автообновления
-- Выполнить в Supabase SQL Editor

-- ============================================
-- 1. Таблица jobs: поиск по названию, описанию, адресу
-- ============================================
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs USING GIN(search_vector);

-- Функция обновления search_vector для jobs
CREATE OR REPLACE FUNCTION jobs_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.organization_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(NEW.object_description, '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(NEW.detailed_description, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.work_type, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.address, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_jobs_search ON jobs;
CREATE TRIGGER trg_jobs_search BEFORE INSERT OR UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION jobs_search_update();

-- Обновить существующие записи
UPDATE jobs SET search_vector =
    setweight(to_tsvector('russian', coalesce(organization_name, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(object_description, '')), 'B') ||
    setweight(to_tsvector('russian', coalesce(detailed_description, '')), 'C') ||
    setweight(to_tsvector('russian', coalesce(work_type, '')), 'C') ||
    setweight(to_tsvector('russian', coalesce(address, '')), 'D');

-- ============================================
-- 2. Таблица profiles: поиск трудников по имени, навыкам, био, городу
-- ============================================
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS search_vector tsvector;
CREATE INDEX IF NOT EXISTS idx_profiles_search ON profiles USING GIN(search_vector);

CREATE OR REPLACE FUNCTION profiles_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.full_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(array_to_string(NEW.skills, ' '), '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(NEW.bio, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.city, '')), 'D');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_profiles_search ON profiles;
CREATE TRIGGER trg_profiles_search BEFORE INSERT OR UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION profiles_search_update();

-- Обновить существующие записи
UPDATE profiles SET search_vector =
    setweight(to_tsvector('russian', coalesce(full_name, '')), 'A') ||
    setweight(to_tsvector('russian', coalesce(array_to_string(skills, ' '), '')), 'B') ||
    setweight(to_tsvector('russian', coalesce(bio, '')), 'C') ||
    setweight(to_tsvector('russian', coalesce(city, '')), 'D');
