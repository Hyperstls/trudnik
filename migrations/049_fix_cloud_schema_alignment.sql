-- ============================================================================
-- Миграция 049: Приведение локальной схемы в соответствие с облачным Supabase
-- Дата: 2026-06-21
-- Контекст: Миграция 030 заменила облачные колонки jobs (organization_name,
--   object_description, work_type, detailed_description и др.) на упрощённые
--   title, description, salary. Это сломало preseed_test_data.py, тестовые
--   фикстуры и триггеры полнотекстового поиска.
--   Данная миграция восстанавливает облачную схему.
-- Идемпотентна: все операции с IF EXISTS / IF NOT EXISTS.
-- ============================================================================

-- ============================================================================
-- ШАГ 1: Восстановить облачные колонки в jobs
-- ============================================================================

-- 1a. organization_name — название организации/задания (облачная схема: text)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS organization_name text NOT NULL DEFAULT '';

-- 1b. org_description — описание организации
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS org_description text NOT NULL DEFAULT '';

-- 1c. object_description — краткое описание объекта работ
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS object_description text NOT NULL DEFAULT '';

-- 1d. work_type — тип/категория работ (было заменено на salary)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS work_type varchar(100) NOT NULL DEFAULT '';

-- 1e. detailed_description — полное описание (было заменено на description)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS detailed_description text NOT NULL DEFAULT '';

-- 1f. date_time — дата и время выполнения
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS date_time timestamptz;

-- 1g. payment_amount — сумма оплаты (было заменено на salary)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payment_amount numeric;

-- 1h. city — город
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS city varchar(255);

-- 1i. lat — широта
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lat double precision;

-- 1j. lng — долгота
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lng double precision;


-- ============================================================================
-- ШАГ 2: Перенести данные из локальных колонок в облачные и удалить локальные
-- ============================================================================

-- 2a. Перенос title -> organization_name (только если облачная колонка пуста)
UPDATE jobs SET organization_name = title
WHERE title IS NOT NULL AND title <> ''
  AND (organization_name IS NULL OR organization_name = '');

-- 2b. Перенос description -> detailed_description
UPDATE jobs SET detailed_description = description
WHERE description IS NOT NULL AND description <> ''
  AND (detailed_description IS NULL OR detailed_description = '');

-- 2c. Перенос salary -> payment_amount (с приведением типа)
UPDATE jobs SET payment_amount = salary::numeric
WHERE salary IS NOT NULL
  AND payment_amount IS NULL;

-- 2d. Удалить локальные колонки
ALTER TABLE jobs DROP COLUMN IF EXISTS title;
ALTER TABLE jobs DROP COLUMN IF EXISTS description;
ALTER TABLE jobs DROP COLUMN IF EXISTS salary;


-- ============================================================================
-- ШАГ 3: Пересоздать триггерную функцию jobs_search_update (облачная версия)
-- ============================================================================

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

-- Пересоздать триггер (DROP + CREATE для гарантии)
DROP TRIGGER IF EXISTS trg_jobs_search ON jobs;
CREATE TRIGGER trg_jobs_search BEFORE INSERT OR UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION jobs_search_update();


-- ============================================================================
-- ШАГ 4: Пересоздать триггерную функцию profiles_search_update (облачная версия)
-- ============================================================================

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

-- Пересоздать триггер (DROP + CREATE для гарантии)
DROP TRIGGER IF EXISTS trg_profiles_search ON profiles;
CREATE TRIGGER trg_profiles_search BEFORE INSERT OR UPDATE ON profiles
    FOR EACH ROW EXECUTE FUNCTION profiles_search_update();


-- ============================================================================
-- ГОТОВО!
-- ============================================================================
