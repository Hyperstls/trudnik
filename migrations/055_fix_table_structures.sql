-- ============================================================================
-- Миграция 055: Исправление структуры таблиц под облачную схему
-- Дата: 2026-06-21
-- Контекст: После сравнения с облачной схемой выявлены расхождения в структуре:
--   employer_details, favorites, blacklists, job_photos, invitations, ratings.
-- 
-- ВАЖНО (из примечаний плана):
--   - НЕ меняем PK-типы (notifications, push_subscriptions, messages — оставляем как есть)
--   - НЕ удаляем суррогатные id из blacklists/favorites (безопасность)
--   - Исправляем только колонки, которые не нарушают существующие FK
-- Идемпотентна: все операции с IF EXISTS / IF NOT EXISTS.
-- ============================================================================

-- ============================================================================
-- ШАГ 1: employer_details — привести к облачной схеме (name/description/address/city/lat/lng)
-- ============================================================================

-- 1a. Добавить недостающие облачные колонки
ALTER TABLE employer_details ADD COLUMN IF NOT EXISTS name text NOT NULL DEFAULT '';
ALTER TABLE employer_details ADD COLUMN IF NOT EXISTS description text;
ALTER TABLE employer_details ADD COLUMN IF NOT EXISTS address text;
ALTER TABLE employer_details ADD COLUMN IF NOT EXISTS city text;
ALTER TABLE employer_details ADD COLUMN IF NOT EXISTS lat double precision;
ALTER TABLE employer_details ADD COLUMN IF NOT EXISTS lng double precision;

-- 1b. Перенести данные из company_name в name (если company_name существует)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'employer_details'
          AND column_name = 'company_name'
    ) THEN
        -- Копируем данные
        UPDATE employer_details SET name = company_name
        WHERE (name IS NULL OR name = '')
          AND company_name IS NOT NULL AND company_name <> '';
    END IF;
END $$;

-- ============================================================================
-- ШАГ 2: favorites — добавить favorite_type (облачная схема: text NOT NULL DEFAULT 'worker')
-- ============================================================================

ALTER TABLE favorites ADD COLUMN IF NOT EXISTS favorite_type text NOT NULL DEFAULT 'worker';

-- Обновить существующие записи — все существующие избранные считаем worker-типом
UPDATE favorites SET favorite_type = 'worker' WHERE favorite_type IS NULL OR favorite_type = '';

-- ============================================================================
-- ШАГ 3: job_photos — переименовать url→photo_url, добавить order_num
-- ============================================================================

-- 3a. Переименовать url в photo_url (если url существует, а photo_url нет)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'job_photos'
          AND column_name = 'url'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'job_photos'
          AND column_name = 'photo_url'
    ) THEN
        ALTER TABLE job_photos RENAME COLUMN url TO photo_url;
    ELSIF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'job_photos'
          AND column_name = 'photo_url'
    ) THEN
        -- На всякий случай — создаём photo_url если ни url ни photo_url нет
        ALTER TABLE job_photos ADD COLUMN photo_url text NOT NULL DEFAULT '';
    END IF;
END $$;

-- 3b. Добавить order_num
ALTER TABLE job_photos ADD COLUMN IF NOT EXISTS order_num integer DEFAULT 0;

-- ============================================================================
-- ШАГ 4: invitations — убрать FK на auth.users (оставить как простые UUID)
-- ============================================================================

-- Удаляем FK если они есть и ссылаются на auth.users
ALTER TABLE invitations DROP CONSTRAINT IF EXISTS invitations_employer_id_fkey;
ALTER TABLE invitations DROP CONSTRAINT IF EXISTS invitations_worker_id_fkey;

-- Добавляем колонку message (облачная схема)
ALTER TABLE invitations ADD COLUMN IF NOT EXISTS message text;

-- Добавляем колонку responded_at (облачная схема)
ALTER TABLE invitations ADD COLUMN IF NOT EXISTS responded_at timestamptz;

-- ============================================================================
-- ШАГ 5: ratings — добавить updated_at
-- ============================================================================

ALTER TABLE ratings ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

-- ============================================================================
-- ШАГ 6: jobs.date_time — убедиться что NOT NULL (облачная схема)
-- ============================================================================

DO $$
DECLARE
    _is_nullable text;
BEGIN
    SELECT is_nullable INTO _is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'jobs'
      AND column_name = 'date_time';

    IF _is_nullable = 'YES' THEN
        -- Заполняем NULL значения дефолтной датой
        UPDATE jobs SET date_time = created_at
        WHERE date_time IS NULL AND created_at IS NOT NULL;
        UPDATE jobs SET date_time = now()
        WHERE date_time IS NULL;

        -- Меняем на NOT NULL
        ALTER TABLE jobs ALTER COLUMN date_time SET NOT NULL;
    END IF;
END $$;

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
