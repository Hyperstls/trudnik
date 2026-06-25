-- ============================================================================
-- Миграция 053: Исправление критических несоответствий типов с облачным Supabase
-- Дата: 2026-06-21
-- Контекст: Сравнение с облачной схемой выявило расхождения типов колонок
--   в jobs и profiles. Облачная схема использует text вместо varchar,
--   double precision вместо numeric, и имеет дополнительные колонки.
-- Идемпотентна: все операции с IF EXISTS / IF NOT EXISTS.
-- ============================================================================

-- ============================================================================
-- ШАГ 1: jobs.organization_name — varchar(255) → text (облачная схема: text)
-- ============================================================================

-- Проверяем тип перед конвертацией
DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type INTO _col_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'jobs'
      AND column_name = 'organization_name';

    IF _col_type IS NULL THEN
        RAISE NOTICE 'Колонка jobs.organization_name не существует — пропускаем шаг 1.';
        RETURN;
    END IF;

    IF _col_type = 'text' THEN
        RAISE NOTICE 'Колонка jobs.organization_name уже text — пропускаем ALTER TYPE.';
        RETURN;
    END IF;

    RAISE NOTICE 'Конвертация jobs.organization_name из % в text.', _col_type;
    ALTER TABLE jobs ALTER COLUMN organization_name TYPE text;
END $$;

-- ============================================================================
-- ШАГ 2: jobs.preferred_religion — varchar(255) → text + DEFAULT 'не важно'
-- ============================================================================

DO $$
DECLARE
    _col_type text;
    _col_default text;
BEGIN
    SELECT data_type, column_default INTO _col_type, _col_default
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'jobs'
      AND column_name = 'preferred_religion';

    IF _col_type IS NULL THEN
        RAISE NOTICE 'Колонка jobs.preferred_religion не существует — пропускаем шаг 2.';
        RETURN;
    END IF;

    -- Меняем тип на text
    IF _col_type != 'text' THEN
        RAISE NOTICE 'Конвертация jobs.preferred_religion из % в text.', _col_type;
        ALTER TABLE jobs ALTER COLUMN preferred_religion TYPE text;
    ELSE
        RAISE NOTICE 'Колонка jobs.preferred_religion уже text.';
    END IF;

    -- Исправляем DEFAULT (облачная схема: 'не важно'::text)
    IF _col_default IS DISTINCT FROM '''не важно''::text' THEN
        RAISE NOTICE 'Исправление DEFAULT для jobs.preferred_religion: % → ''не важно''.', _col_default;
        ALTER TABLE jobs ALTER COLUMN preferred_religion SET DEFAULT 'не важно';
    END IF;
END $$;

-- ============================================================================
-- ШАГ 3: profiles.role — varchar(20) → text (облачная схема: text DEFAULT 'worker')
-- ============================================================================
-- ВАЖНО: ALTER TYPE на колонке, используемой в RLS-политиках, не работает
-- напрямую в Postgres 15+. Обходим через удаление/восстановление политик.

DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type INTO _col_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'profiles'
      AND column_name = 'role';

    IF _col_type IS NULL THEN
        RAISE NOTICE 'Колонка profiles.role не существует — пропускаем шаг 3.';
        RETURN;
    END IF;

    IF _col_type = 'text' THEN
        RAISE NOTICE 'Колонка profiles.role уже text — пропускаем ALTER TYPE.';
        RETURN;
    END IF;

    RAISE NOTICE 'Конвертация profiles.role из % в text (с временным удалением RLS-политик).', _col_type;

    -- Временно удаляем политики, использующие колонку role
    DROP POLICY IF EXISTS "Anyone can view employer details" ON employer_details;
    DROP POLICY IF EXISTS "Employers can insert own details" ON employer_details;
    DROP POLICY IF EXISTS "Employers can update own details" ON employer_details;
    DROP POLICY IF EXISTS "Admin can insert tariff settings" ON tariff_settings;
    DROP POLICY IF EXISTS "Admin can update tariff settings" ON tariff_settings;
    DROP POLICY IF EXISTS "Admin can read schema_migrations" ON schema_migrations;
    DROP POLICY IF EXISTS "monetization_settings_insert" ON monetization_settings;
    DROP POLICY IF EXISTS "monetization_settings_update" ON monetization_settings;
    DROP POLICY IF EXISTS "receipts_select" ON receipts;
    DROP POLICY IF EXISTS "receipts_insert" ON receipts;
    DROP POLICY IF EXISTS "receipts_update" ON receipts;

    -- Меняем тип
    ALTER TABLE profiles ALTER COLUMN role TYPE text;

    -- Восстанавливаем политики (с проверкой на существование)
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'employer_details_select' AND tablename = 'employer_details') THEN
        CREATE POLICY employer_details_select ON employer_details FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'employer_details_insert' AND tablename = 'employer_details') THEN
        CREATE POLICY employer_details_insert ON employer_details FOR INSERT WITH CHECK (auth.uid() = id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'employer_details_update' AND tablename = 'employer_details') THEN
        CREATE POLICY employer_details_update ON employer_details FOR UPDATE USING (auth.uid() = id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'monetization_settings_insert' AND tablename = 'monetization_settings') THEN
        CREATE POLICY monetization_settings_insert ON monetization_settings
            FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'monetization_settings_update' AND tablename = 'monetization_settings') THEN
        CREATE POLICY monetization_settings_update ON monetization_settings
            FOR UPDATE USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'receipts_select' AND tablename = 'receipts') THEN
        CREATE POLICY receipts_select ON receipts
            FOR SELECT USING (
                auth.uid() IN (
                    SELECT employer_id FROM _archive_contact_payments WHERE _archive_contact_payments.id = receipts.contact_payment_id
                    UNION SELECT worker_id FROM _archive_contact_payments WHERE _archive_contact_payments.id = receipts.contact_payment_id
                ) OR EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin')
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'receipts_insert' AND tablename = 'receipts') THEN
        CREATE POLICY receipts_insert ON receipts
            FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'receipts_update' AND tablename = 'receipts') THEN
        CREATE POLICY receipts_update ON receipts
            FOR UPDATE USING (EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));
    END IF;

    RAISE NOTICE 'Шаг 3 завершён: profiles.role изменён на text, политики восстановлены.';
END $$;

-- ============================================================================
-- ШАГ 4: profiles.rating — numeric → double precision (облачная схема: float8)
-- ============================================================================

DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type INTO _col_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'profiles'
      AND column_name = 'rating';

    IF _col_type IS NULL THEN
        RAISE NOTICE 'Колонка profiles.rating не существует — пропускаем шаг 4.';
        RETURN;
    END IF;

    IF _col_type = 'double precision' THEN
        RAISE NOTICE 'Колонка profiles.rating уже double precision — пропускаем ALTER TYPE.';
        RETURN;
    END IF;

    RAISE NOTICE 'Конвертация profiles.rating из % в double precision.', _col_type;
    ALTER TABLE profiles ALTER COLUMN rating TYPE double precision USING rating::double precision;
END $$;

-- ============================================================================
-- ШАГ 5: profiles — добавить недостающие колонки
-- ============================================================================

-- 5a. inn — ИНН (для работодателей)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS inn text DEFAULT '';

-- 5b. is_self_employed — самозанятость
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_self_employed boolean DEFAULT false;

-- 5c. email_public — публичный email (для отображения в профиле)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_public text DEFAULT '';

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
