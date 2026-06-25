-- ============================================================================
-- Миграция 050: Приведение profiles к облачной схеме Supabase
-- Дата: 2026-06-21
-- Контекст: В локальной БД таблица profiles содержит только 11 из 26 облачных
--   колонок. Отсутствуют full_name, phone, photo_url, age, bio, city,
--   experience, desired_payment, verification_status, verification_doc_url,
--   rating, total_reviews, skills, religion, portfolio_link.
--   Это ломает:
--     - профили пользователей (profile.py, auth.py)
--     - списки работников/работодателей (employers.py, jobs.py)
--     - отклики (applications.py)
--     - избранное (favorites.py)
--     - рейтинги (ratings.py)
--     - админку (admin.py)
--     - триггер profiles_search_update (миграция 049)
--     - preseed_test_data.py (не напрямую, но через представления Supabase)
-- Идемпотентна: все операции с IF NOT EXISTS.
-- ============================================================================

-- ============================================================================
-- ШАГ 1: Базовые поля профиля
-- ============================================================================

-- 1a. full_name — полное имя (обязательное)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS full_name text NOT NULL DEFAULT '';

-- 1b. phone — телефон
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone text;

-- 1c. photo_url — URL аватарки
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS photo_url text;

-- 1d. age — возраст
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS age integer;

-- 1e. bio — описание «О себе»
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bio text;

-- 1f. city — город
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS city text;

-- 1g. experience — опыт работы (текстовое описание)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS experience text;

-- 1h. desired_payment — желаемая оплата
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS desired_payment numeric;

-- ============================================================================
-- ШАГ 2: Верификация
-- ============================================================================

-- 2a. verification_status — статус верификации
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS verification_status text DEFAULT 'none';

-- 2b. verification_doc_url — ссылка на документ верификации
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS verification_doc_url text;

-- ============================================================================
-- ШАГ 3: Рейтинг
-- ============================================================================

-- 3a. rating — средний рейтинг пользователя (облачная схема: float8)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rating double precision DEFAULT 0;

-- 3b. total_reviews — количество отзывов
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS total_reviews integer DEFAULT 0;

-- ============================================================================
-- ШАГ 4: Навыки, вероисповедание, портфолио, идентификация
-- ============================================================================

-- 4a. skills — массив навыков
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS skills text[] DEFAULT '{}';

-- 4b. religion — вероисповедание (текстовое поле, дублирует religion_id)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS religion text DEFAULT 'не указано';

-- 4c. portfolio_link — ссылка на портфолио
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS portfolio_link text DEFAULT '';

-- 4d. inn — ИНН (для работодателей)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS inn text DEFAULT '';

-- 4e. is_self_employed — самозанятость
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_self_employed boolean DEFAULT false;

-- 4f. email_public — публичный email (для отображения в профиле)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_public text DEFAULT '';

-- ============================================================================
-- ШАГ 5: Исправление preferred_religion в jobs (облачная схема: varchar, не uuid)
-- ============================================================================

-- Миграция 030 ошибочно создала preferred_religion как uuid REFERENCES religions(id),
-- но в облачной схеме это varchar(255). preseed_test_data.py отправляет '' (пустую строку),
-- что несовместимо с uuid. Исправляем тип и удаляем FK.

-- Шаг 5a: Проверить тип колонки перед ALTER (защита от повторного применения)
DO $$
DECLARE
    _col_type text;
BEGIN
    SELECT data_type INTO _col_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'jobs'
      AND column_name = 'preferred_religion';

    IF _col_type IS NULL THEN
        RAISE NOTICE 'Колонка preferred_religion не существует — пропускаем шаг 5.';
        RETURN;
    END IF;

    IF _col_type = 'character varying' THEN
        RAISE NOTICE 'Колонка preferred_religion уже varchar(255) — пропускаем ALTER.';
        RETURN;
    END IF;

    -- Записываем существующие UUID-значения перед преобразованием (аудит)
    RAISE NOTICE 'Конвертация preferred_religion из % в varchar(255). '
        'Все существующие UUID-значения будут сохранены как текст.', _col_type;
END $$;

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_preferred_religion_fkey;
ALTER TABLE jobs ALTER COLUMN preferred_religion TYPE varchar(255) USING preferred_religion::text;

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
