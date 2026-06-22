-- ============================================================================
-- BOOTSTRAP ДЛЯ ПУСТОЙ БД AMVERA POSTGRESQL
-- Файл: migrations/067_bootstrap_amvera.sql
-- Дата: 2026-06-23
-- ============================================================================
--
-- НАЗНАЧЕНИЕ:
--   Полный bootstrap для абсолютно пустой БД PostgreSQL на Amvera.
--   Создаёт ВСЁ с нуля: расширения, роли, таблицы, индексы, триггеры,
--   RLS-политики, RPC-функции, права доступа и администратора.
--
-- ИНСТРУКЦИЯ:
--   1. Откройте pgAdmin, подключитесь к БД postgres (Amvera trudnik-db-superuser)
--   2. Откройте этот файл и нажмите Execute (F5)
--   3. Скрипт полностью идемпотентен — можно запускать повторно
--
-- ЧТО ВКЛЮЧЕНО:
--   - Расширения: pgcrypto, postgis, pg_trgm
--   - Роли: anon, authenticated, service_role
--   - 24 таблицы (все колонки, constraints, foreign keys)
--   - Seed-данные (religions, skills, tariff_settings, monetization_settings)
--   - Индексы для всех таблиц
--   - Триггеры полнотекстового поиска (jobs, profiles)
--   - RLS-политики для всех таблиц (JWT-based через current_setting)
--   - RPC-функции: 3 auth + 8 атомарных + exec_sql + accept/reject/delete + get_job_stats + nearby_jobs
--   - Права доступа (REVOKE/GRANT)
--   - Администратор admin@test.ru / Step@1986
--
-- АРХИТЕКТУРА:
--   - Авторизация через JWT (Flask → PostgREST)
--   - RLS использует current_setting('request.jwt.claim.xxx', true)
--   - Все операции идемпотентны (IF NOT EXISTS, CREATE OR REPLACE, ON CONFLICT)
-- ============================================================================

-- ============================================
-- СЕКЦИЯ 1: РАСШИРЕНИЯ
-- ============================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================
-- СЕКЦИЯ 2: РОЛИ ДЛЯ POSTGREST
-- ============================================

DO $$ BEGIN
    CREATE ROLE anon WITH NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE ROLE authenticated WITH NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE ROLE service_role WITH NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Даём права текущему пользователю (postgres/trudnikapp)
GRANT anon, authenticated, service_role TO CURRENT_USER;

-- ============================================
-- СЕКЦИЯ 3: СОЗДАНИЕ ТАБЛИЦ
-- Порядок: от базовых к зависимым (учитывает FK)
-- ============================================

-- 3.1 profiles — базовая таблица пользователей
-- Включает колонки из run_all_safe + avatar_url, ratings_count, email, password_hash
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role text NOT NULL DEFAULT 'worker',
    full_name text NOT NULL DEFAULT '',
    phone text,
    photo_url text,
    avatar_url text,
    age integer,
    bio text,
    city text,
    experience text,
    desired_payment numeric,
    verification_status text DEFAULT 'none',
    verification_doc_url text,
    rating double precision DEFAULT 0,
    total_reviews integer DEFAULT 0,
    ratings_count integer DEFAULT 0,
    skills text[] DEFAULT '{}',
    religion text DEFAULT 'не указано',
    religion_id UUID,
    portfolio_link text DEFAULT '',
    inn text DEFAULT '',
    is_self_employed boolean DEFAULT false,
    email_public text DEFAULT '',
    contact text,
    notification_prefs JSONB DEFAULT '{}'::jsonb,
    search_vector tsvector,
    email text,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT NOW(),
    updated_at timestamptz NOT NULL DEFAULT NOW()
);

-- 3.2 religions — справочник вероисповеданий
CREATE TABLE IF NOT EXISTS religions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO religions (name) VALUES
    ('Православие'),
    ('Католичество'),
    ('Ислам'),
    ('Иудаизм'),
    ('Буддизм'),
    ('Не важно')
ON CONFLICT (name) DO NOTHING;

-- 3.3 skills — справочник навыков
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO skills (name) VALUES
    ('Уборка'),
    ('Повар'),
    ('Садоводство'),
    ('Плотник'),
    ('Электрик'),
    ('Маляр'),
    ('Сантехник'),
    ('Водитель'),
    ('Разнорабочий'),
    ('Столяр'),
    ('Разгрузка'),
    ('Штукатур'),
    ('Плиточник'),
    ('Кровельщик'),
    ('Сварщик'),
    ('IT'),
    ('Бухгалтер'),
    ('Секретарь'),
    ('Охрана'),
    ('Уход за животными')
ON CONFLICT (name) DO NOTHING;

-- 3.4 jobs — задания (→ profiles)
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL,
    organization_name text NOT NULL DEFAULT '',
    org_description text NOT NULL DEFAULT '',
    object_description text NOT NULL DEFAULT '',
    work_type varchar(100) NOT NULL DEFAULT '',
    detailed_description text NOT NULL DEFAULT '',
    address varchar(500),
    city varchar(255),
    lat double precision,
    lng double precision,
    date_time timestamptz NOT NULL DEFAULT now(),
    payment_amount numeric,
    status varchar(20) NOT NULL DEFAULT 'open',
    max_workers integer DEFAULT 1,
    current_workers integer DEFAULT 0,
    tariff varchar(20) DEFAULT 'standard',
    is_paid boolean DEFAULT false,
    paid_at timestamptz,
    expires_at timestamptz,
    preferred_religion text DEFAULT 'не важно',
    search_vector tsvector,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Идемпотентные constraint-ы для jobs
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS fk_jobs_employer_id;
ALTER TABLE jobs ADD CONSTRAINT fk_jobs_employer_id FOREIGN KEY (employer_id) REFERENCES profiles(id) ON DELETE CASCADE;

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check CHECK (status IN ('open', 'completed', 'cancelled'));

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_max_workers_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_max_workers_check CHECK (max_workers >= 1);

ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_current_workers_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_current_workers_check CHECK (current_workers >= 0 AND current_workers <= max_workers);

-- 3.5 user_skills — связь пользователь-навыки (→ profiles + skills)
CREATE TABLE IF NOT EXISTS user_skills (
    user_id UUID NOT NULL,
    skill_id UUID NOT NULL,
    PRIMARY KEY (user_id, skill_id)
);

-- Идемпотентные constraint-ы для user_skills
ALTER TABLE user_skills DROP CONSTRAINT IF EXISTS fk_user_skills_user_id;
ALTER TABLE user_skills ADD CONSTRAINT fk_user_skills_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE user_skills DROP CONSTRAINT IF EXISTS fk_user_skills_skill_id;
ALTER TABLE user_skills ADD CONSTRAINT fk_user_skills_skill_id FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE;


-- 3.6 job_skills — связь задание-навыки (→ jobs + skills)
CREATE TABLE IF NOT EXISTS job_skills (
    job_id UUID NOT NULL,
    skill_id UUID NOT NULL,
    PRIMARY KEY (job_id, skill_id)
);

-- Идемпотентные constraint-ы для job_skills
ALTER TABLE job_skills DROP CONSTRAINT IF EXISTS fk_job_skills_job_id;
ALTER TABLE job_skills ADD CONSTRAINT fk_job_skills_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;
ALTER TABLE job_skills DROP CONSTRAINT IF EXISTS fk_job_skills_skill_id;
ALTER TABLE job_skills ADD CONSTRAINT fk_job_skills_skill_id FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE;


-- 3.7 applications — отклики (→ jobs + profiles)
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    worker_id UUID NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'pending',
    contact_paid boolean DEFAULT false,
    contact_payment_id UUID,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, worker_id)
);

-- Идемпотентные constraint-ы для applications
ALTER TABLE applications DROP CONSTRAINT IF EXISTS fk_applications_job_id;
ALTER TABLE applications ADD CONSTRAINT fk_applications_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;
ALTER TABLE applications DROP CONSTRAINT IF EXISTS fk_applications_worker_id;
ALTER TABLE applications ADD CONSTRAINT fk_applications_worker_id FOREIGN KEY (worker_id) REFERENCES profiles(id) ON DELETE CASCADE;

ALTER TABLE applications DROP CONSTRAINT IF EXISTS applications_status_check;
ALTER TABLE applications ADD CONSTRAINT applications_status_check CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn'));

-- 3.8 messages — чат (→ profiles + applications)
CREATE TABLE IF NOT EXISTS messages (
    id bigint PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    sender_id UUID NOT NULL,
    application_id UUID,
    content text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Идемпотентные constraint-ы для messages
ALTER TABLE messages DROP CONSTRAINT IF EXISTS fk_messages_sender_id;
ALTER TABLE messages ADD CONSTRAINT fk_messages_sender_id FOREIGN KEY (sender_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE messages DROP CONSTRAINT IF EXISTS fk_messages_application_id;
ALTER TABLE messages ADD CONSTRAINT fk_messages_application_id FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE;


-- 3.9 ratings — оценки (→ profiles + jobs)
CREATE TABLE IF NOT EXISTS ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rated_user_id UUID NOT NULL,
    rater_user_id UUID NOT NULL,
    job_id UUID,
    rating_type VARCHAR(20) NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at timestamptz DEFAULT now(),
    CONSTRAINT ratings_rater_job_unique UNIQUE (rater_user_id, job_id)
);

-- Идемпотентные constraint-ы для ratings
ALTER TABLE ratings DROP CONSTRAINT IF EXISTS fk_ratings_rated_user_id;
ALTER TABLE ratings ADD CONSTRAINT fk_ratings_rated_user_id FOREIGN KEY (rated_user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE ratings DROP CONSTRAINT IF EXISTS fk_ratings_rater_user_id;
ALTER TABLE ratings ADD CONSTRAINT fk_ratings_rater_user_id FOREIGN KEY (rater_user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE ratings DROP CONSTRAINT IF EXISTS fk_ratings_job_id;
ALTER TABLE ratings ADD CONSTRAINT fk_ratings_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;

ALTER TABLE ratings DROP CONSTRAINT IF EXISTS ratings_rating_type_check;
ALTER TABLE ratings ADD CONSTRAINT ratings_rating_type_check CHECK (rating_type IN ('worker', 'employer'));

ALTER TABLE ratings DROP CONSTRAINT IF EXISTS ratings_target_type_check;
ALTER TABLE ratings ADD CONSTRAINT ratings_target_type_check CHECK (target_type IN ('worker', 'employer'));

ALTER TABLE ratings DROP CONSTRAINT IF EXISTS ratings_rating_check;
ALTER TABLE ratings ADD CONSTRAINT ratings_rating_check CHECK (rating >= 1 AND rating <= 5);

-- 3.10 notifications — уведомления (→ profiles + jobs + applications)
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    job_id UUID,
    application_id UUID,
    shift_id UUID,
    data JSONB DEFAULT '{}'::jsonb,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Идемпотентные constraint-ы для notifications
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_user_id;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_job_id;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL;
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS fk_notifications_application_id;
ALTER TABLE notifications ADD CONSTRAINT fk_notifications_application_id FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE SET NULL;


-- 3.11 favorites — избранные работники (→ profiles)
CREATE TABLE IF NOT EXISTS favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    target_id UUID NOT NULL,
    favorite_type text NOT NULL DEFAULT 'worker',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, target_id, favorite_type)
);

-- Идемпотентные constraint-ы для favorites
ALTER TABLE favorites DROP CONSTRAINT IF EXISTS fk_favorites_user_id;
ALTER TABLE favorites ADD CONSTRAINT fk_favorites_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE favorites DROP CONSTRAINT IF EXISTS fk_favorites_target_id;
ALTER TABLE favorites ADD CONSTRAINT fk_favorites_target_id FOREIGN KEY (target_id) REFERENCES profiles(id) ON DELETE CASCADE;


-- 3.12 blacklists — чёрные списки (→ profiles)
CREATE TABLE IF NOT EXISTS blacklists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    blocked_user_id UUID NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, blocked_user_id)
);

-- Идемпотентные constraint-ы для blacklists
ALTER TABLE blacklists DROP CONSTRAINT IF EXISTS fk_blacklists_user_id;
ALTER TABLE blacklists ADD CONSTRAINT fk_blacklists_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE blacklists DROP CONSTRAINT IF EXISTS fk_blacklists_blocked_user_id;
ALTER TABLE blacklists ADD CONSTRAINT fk_blacklists_blocked_user_id FOREIGN KEY (blocked_user_id) REFERENCES profiles(id) ON DELETE CASCADE;


-- 3.13 job_favorites — избранные задания (→ profiles + jobs)
CREATE TABLE IF NOT EXISTS job_favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    job_id UUID NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(user_id, job_id)
);

-- Идемпотентные constraint-ы для job_favorites
ALTER TABLE job_favorites DROP CONSTRAINT IF EXISTS fk_job_favorites_user_id;
ALTER TABLE job_favorites ADD CONSTRAINT fk_job_favorites_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;
ALTER TABLE job_favorites DROP CONSTRAINT IF EXISTS fk_job_favorites_job_id;
ALTER TABLE job_favorites ADD CONSTRAINT fk_job_favorites_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;


-- 3.14 job_photos — фото заданий (→ jobs)
CREATE TABLE IF NOT EXISTS job_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    photo_url text NOT NULL DEFAULT '',
    order_num integer DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Идемпотентные constraint-ы для job_photos
ALTER TABLE job_photos DROP CONSTRAINT IF EXISTS fk_job_photos_job_id;
ALTER TABLE job_photos ADD CONSTRAINT fk_job_photos_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;


-- 3.15 employer_details — детали работодателя (→ profiles)
CREATE TABLE IF NOT EXISTS employer_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE,
    name text NOT NULL DEFAULT '',
    description text,
    address text,
    city text,
    lat double precision,
    lng double precision,
    company_name varchar(255),
    inn varchar(12),
    is_self_employed boolean DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Идемпотентные constraint-ы для employer_details
ALTER TABLE employer_details DROP CONSTRAINT IF EXISTS fk_employer_details_user_id;
ALTER TABLE employer_details ADD CONSTRAINT fk_employer_details_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;


-- 3.16 invitations — приглашения (→ jobs)
CREATE TABLE IF NOT EXISTS invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    employer_id UUID NOT NULL,
    worker_id UUID NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    UNIQUE(job_id, worker_id)
);

-- Идемпотентные constraint-ы для invitations
ALTER TABLE invitations DROP CONSTRAINT IF EXISTS fk_invitations_job_id;
ALTER TABLE invitations ADD CONSTRAINT fk_invitations_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;

ALTER TABLE invitations DROP CONSTRAINT IF EXISTS invitations_status_check;
ALTER TABLE invitations ADD CONSTRAINT invitations_status_check CHECK (status IN ('pending', 'accepted', 'rejected'));

-- 3.17 job_payments — платежи за публикацию (→ jobs)
CREATE TABLE IF NOT EXISTS job_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    employer_id UUID NOT NULL,
    amount INTEGER NOT NULL,
    tariff VARCHAR(20) DEFAULT 'standard',
    type VARCHAR(30) DEFAULT 'publication',
    status VARCHAR(20) DEFAULT 'pending',
    transaction_id VARCHAR(255),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Идемпотентные constraint-ы для job_payments
ALTER TABLE job_payments DROP CONSTRAINT IF EXISTS fk_job_payments_job_id;
ALTER TABLE job_payments ADD CONSTRAINT fk_job_payments_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;


-- 3.18 tariff_settings — настройки тарифов
CREATE TABLE IF NOT EXISTS tariff_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tariff_key VARCHAR(30) UNIQUE NOT NULL,
    price INTEGER NOT NULL,
    duration_days INTEGER NOT NULL DEFAULT 30,
    renewal_price INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO tariff_settings (tariff_key, price, duration_days, renewal_price)
VALUES ('standard', 490, 30, 290)
ON CONFLICT (tariff_key) DO NOTHING;

-- 3.19 monetization_settings — настройки монетизации
CREATE TABLE IF NOT EXISTS monetization_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO monetization_settings (key, value) VALUES
    ('contact_price', '290'),
    ('owner_inn', '')
ON CONFLICT (key) DO NOTHING;

-- 3.20 _archive_contact_payments — архив платежей за контакты
CREATE TABLE IF NOT EXISTS _archive_contact_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL,
    worker_id UUID NOT NULL,
    job_id UUID NOT NULL,
    application_id UUID,
    amount INTEGER NOT NULL DEFAULT 290,
    status TEXT NOT NULL DEFAULT 'pending',
    transaction_id TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    paid_at TIMESTAMPTZ
);

-- 3.21 receipts — чеки
CREATE TABLE IF NOT EXISTS receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_payment_id UUID,
    church_name TEXT NOT NULL DEFAULT '',
    church_inn TEXT NOT NULL DEFAULT '',
    service_description TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'sent',
    receipt_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    resent_at TIMESTAMPTZ
);

-- 3.22 push_subscriptions — push-подписки (→ profiles)
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, endpoint)
);

-- Идемпотентные constraint-ы для push_subscriptions
ALTER TABLE push_subscriptions DROP CONSTRAINT IF EXISTS fk_push_subscriptions_user_id;
ALTER TABLE push_subscriptions ADD CONSTRAINT fk_push_subscriptions_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;


-- 3.23 email_log — логи email (→ notifications + profiles)
CREATE TABLE IF NOT EXISTS email_log (
    id BIGSERIAL PRIMARY KEY,
    notification_id UUID,
    user_id UUID NOT NULL,
    to_email TEXT,
    subject TEXT,
    template_name VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Идемпотентные constraint-ы для email_log
ALTER TABLE email_log DROP CONSTRAINT IF EXISTS fk_email_log_notification_id;
ALTER TABLE email_log ADD CONSTRAINT fk_email_log_notification_id FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE SET NULL;
ALTER TABLE email_log DROP CONSTRAINT IF EXISTS fk_email_log_user_id;
ALTER TABLE email_log ADD CONSTRAINT fk_email_log_user_id FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE;


-- 3.24 schema_migrations — версионирование
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ DEFAULT now(),
    checksum TEXT
);

-- ============================================
-- СЕКЦИЯ 4: ДОПОЛНИТЕЛЬНЫЕ КОНСТРЕЙНТЫ И АЛЬТЕРЫ
-- ============================================

-- FK для profiles.religion_id (не в CREATE TABLE из-за циклической зависимости)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_name = 'profiles'
          AND ccu.table_name = 'religions'
          AND ccu.column_name = 'id'
    ) THEN
        ALTER TABLE profiles ADD CONSTRAINT fk_profiles_religion_id
            FOREIGN KEY (religion_id) REFERENCES religions(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Уникальный индекс для profiles.email
-- NOTE: без WHERE — иначе ON CONFLICT (email) не сможет использовать partial unique index
CREATE UNIQUE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);

-- Уникальный индекс для job_payments (предотвращение двойной оплаты)
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_payments_paid_unique
ON job_payments (job_id) WHERE status = 'paid';

-- ============================================
-- СЕКЦИЯ 5: ИНДЕКСЫ
-- ============================================

-- Индексы для jobs
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_employer_id ON jobs(employer_id);
CREATE INDEX IF NOT EXISTS idx_jobs_current_workers ON jobs(current_workers);
CREATE INDEX IF NOT EXISTS idx_jobs_status_and_workers ON jobs(status, current_workers, max_workers);
CREATE INDEX IF NOT EXISTS idx_jobs_expires ON jobs(expires_at) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_jobs_search ON jobs USING GIN(search_vector);

-- Индексы для profiles
CREATE INDEX IF NOT EXISTS idx_profiles_search ON profiles USING GIN(search_vector);

-- Индексы для справочников
CREATE INDEX IF NOT EXISTS idx_skills_sort ON skills(sort_order, name);
CREATE INDEX IF NOT EXISTS idx_religions_sort ON religions(sort_order, name);

-- Индексы для applications
CREATE INDEX IF NOT EXISTS idx_applications_contact_payment_id ON applications(contact_payment_id);
CREATE INDEX IF NOT EXISTS idx_applications_worker_id ON applications(worker_id);

-- Индексы для blacklists
CREATE INDEX IF NOT EXISTS idx_blacklists_blocked_user_id ON blacklists(blocked_user_id);

-- Индексы для favorites
CREATE INDEX IF NOT EXISTS idx_favorites_target_id ON favorites(target_id);
CREATE INDEX IF NOT EXISTS idx_favorites_type ON favorites(favorite_type);

-- Индексы для job_favorites
CREATE INDEX IF NOT EXISTS idx_job_favorites_job_id ON job_favorites(job_id);

-- Индексы для job_photos
CREATE INDEX IF NOT EXISTS idx_job_photos_job_id ON job_photos(job_id);

-- Индексы для job_skills
CREATE INDEX IF NOT EXISTS idx_job_skills_skill_id ON job_skills(skill_id);

-- Индексы для messages
CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_application_id ON messages(application_id);

-- Индексы для notifications
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_job_id ON notifications(job_id);
CREATE INDEX IF NOT EXISTS idx_notifications_application_id ON notifications(application_id);

-- Индексы для push_subscriptions
CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_id ON push_subscriptions(user_id);

-- Индексы для ratings
CREATE INDEX IF NOT EXISTS idx_ratings_rated_user ON ratings(rated_user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_rater_user ON ratings(rater_user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_job ON ratings(job_id);

-- Индексы для email_log
CREATE INDEX IF NOT EXISTS idx_email_log_user_id ON email_log(user_id);

-- Индексы для invitations
CREATE INDEX IF NOT EXISTS idx_invitations_worker ON invitations(worker_id);
CREATE INDEX IF NOT EXISTS idx_invitations_employer ON invitations(employer_id);
CREATE INDEX IF NOT EXISTS idx_invitations_job ON invitations(job_id);

-- Индексы для job_payments
CREATE INDEX IF NOT EXISTS idx_job_payments_job ON job_payments(job_id);
CREATE INDEX IF NOT EXISTS idx_job_payments_employer ON job_payments(employer_id);

-- Индексы для user_skills
CREATE INDEX IF NOT EXISTS idx_user_skills_skill_id ON user_skills(skill_id);

-- ============================================
-- СЕКЦИЯ 6: ТРИГГЕРЫ ПОЛНОТЕКСТОВОГО ПОИСКА
-- ============================================

-- 6a. Триггер search_vector для jobs
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

-- 6b. Триггер search_vector для profiles
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

-- ============================================
-- СЕКЦИЯ 7: RLS — ВКЛЮЧЕНИЕ ДЛЯ ВСЕХ ТАБЛИЦ
-- ============================================

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE blacklists ENABLE ROW LEVEL SECURITY;
ALTER TABLE ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE religions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_photos ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE tariff_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE monetization_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE _archive_contact_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_log ENABLE ROW LEVEL SECURITY;

-- ============================================
-- СЕКЦИЯ 8: RLS ПОЛИТИКИ
-- ============================================

-- 8a. profiles
DROP POLICY IF EXISTS "Users can read profiles" ON profiles;
DROP POLICY IF EXISTS "Users can update their own profile" ON profiles;
DROP POLICY IF EXISTS "Service can insert profiles" ON profiles;

CREATE POLICY "Users can read profiles"
    ON profiles FOR SELECT USING (true);

CREATE POLICY "Service can insert profiles"
    ON profiles FOR INSERT WITH CHECK (true);

CREATE POLICY "Users can update their own profile"
    ON profiles FOR UPDATE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = id)
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = id);

-- 8b. jobs
DROP POLICY IF EXISTS "Employers can insert jobs" ON jobs;
DROP POLICY IF EXISTS "Users can read jobs" ON jobs;
DROP POLICY IF EXISTS "Jobs are viewable by everyone" ON jobs;
DROP POLICY IF EXISTS "Employers can update their own jobs" ON jobs;
DROP POLICY IF EXISTS "Employers can delete their own jobs" ON jobs;

CREATE POLICY "Users can read jobs"
    ON jobs FOR SELECT
    USING (status = 'open' OR status = 'completed' OR status = 'cancelled');

CREATE POLICY "Employers can insert jobs"
    ON jobs FOR INSERT
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

CREATE POLICY "Employers can update their own jobs"
    ON jobs FOR UPDATE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id)
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

CREATE POLICY "Employers can delete their own jobs"
    ON jobs FOR DELETE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

-- 8c. applications
DROP POLICY IF EXISTS "Users can insert applications" ON applications;
DROP POLICY IF EXISTS "Users can read their own applications" ON applications;
DROP POLICY IF EXISTS "Users can view own applications" ON applications;
DROP POLICY IF EXISTS "Employers can read applications for their jobs" ON applications;
DROP POLICY IF EXISTS "Employers can update applications" ON applications;
DROP POLICY IF EXISTS "Users can delete own applications" ON applications;
DROP POLICY IF EXISTS "Workers can delete own applications" ON applications;
DROP POLICY IF EXISTS "Employers can update applications on their jobs" ON applications;
DROP POLICY IF EXISTS "Users can update own applications" ON applications;

CREATE POLICY "Users can insert applications"
    ON applications FOR INSERT
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = worker_id);

CREATE POLICY "Users can view own applications"
    ON applications FOR SELECT
    USING (
        current_setting('request.jwt.claim.user_id', true)::uuid = worker_id
        OR current_setting('request.jwt.claim.user_id', true)::uuid IN (
            SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id
        )
    );

CREATE POLICY "Users can update own applications"
    ON applications FOR UPDATE
    USING (
        current_setting('request.jwt.claim.user_id', true)::uuid = worker_id
        OR EXISTS (
            SELECT 1 FROM jobs
            WHERE jobs.id = applications.job_id
            AND jobs.employer_id = current_setting('request.jwt.claim.user_id', true)::uuid
        )
    );

CREATE POLICY "Users can delete own applications"
    ON applications FOR DELETE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = worker_id);

-- 8d. messages
DROP POLICY IF EXISTS "Shift participants can view messages" ON messages;
DROP POLICY IF EXISTS "Shift participants can insert messages" ON messages;
DROP POLICY IF EXISTS "Application participants can view messages" ON messages;
DROP POLICY IF EXISTS "Application participants can insert messages" ON messages;

CREATE POLICY "Application participants can view messages" ON messages
    FOR SELECT USING (
        current_setting('request.jwt.claim.user_id', true)::uuid IN (
            SELECT worker_id FROM applications WHERE applications.id = messages.application_id
            UNION
            SELECT jobs.employer_id FROM applications
            JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.id = messages.application_id
        )
    );

CREATE POLICY "Application participants can insert messages" ON messages
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.user_id', true)::uuid = sender_id
    );

-- 8e. notifications
DROP POLICY IF EXISTS "Users can read their own notifications" ON notifications;
DROP POLICY IF EXISTS "Users can insert notifications" ON notifications;
DROP POLICY IF EXISTS "Service can insert notifications" ON notifications;

CREATE POLICY "Service can insert notifications"
    ON notifications FOR INSERT WITH CHECK (true);

CREATE POLICY "Users can read their own notifications"
    ON notifications FOR SELECT
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- 8f. favorites
DROP POLICY IF EXISTS "Users can insert favorites" ON favorites;
DROP POLICY IF EXISTS "Users can read their own favorites" ON favorites;
DROP POLICY IF EXISTS "Users can delete their own favorites" ON favorites;

CREATE POLICY "Users can insert favorites"
    ON favorites FOR INSERT
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can read their own favorites"
    ON favorites FOR SELECT
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can delete their own favorites"
    ON favorites FOR DELETE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- 8g. blacklists
DROP POLICY IF EXISTS "Users can insert blacklists" ON blacklists;
DROP POLICY IF EXISTS "Users can read their own blacklists" ON blacklists;
DROP POLICY IF EXISTS "Users can delete their own blacklists" ON blacklists;

CREATE POLICY "Users can insert blacklists"
    ON blacklists FOR INSERT
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can read their own blacklists"
    ON blacklists FOR SELECT
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can delete their own blacklists"
    ON blacklists FOR DELETE
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- 8h. ratings
DROP POLICY IF EXISTS "Users can insert ratings" ON ratings;
DROP POLICY IF EXISTS "Users can read ratings" ON ratings;
DROP POLICY IF EXISTS "Anyone can read ratings" ON ratings;
DROP POLICY IF EXISTS "Users can upsert own ratings" ON ratings;
DROP POLICY IF EXISTS "Users can update own ratings" ON ratings;
DROP POLICY IF EXISTS "Admin can manage ratings" ON ratings;

CREATE POLICY "Anyone can read ratings"
    ON ratings FOR SELECT USING (true);

CREATE POLICY "Users can upsert own ratings" ON ratings
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = rater_user_id);

CREATE POLICY "Users can update own ratings" ON ratings
    FOR UPDATE USING (current_setting('request.jwt.claim.user_id', true)::uuid = rater_user_id)
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = rater_user_id);

-- 8i. skills, religions, user_skills, job_skills
DROP POLICY IF EXISTS "read_skills" ON skills;
DROP POLICY IF EXISTS "admin_skills" ON skills;
DROP POLICY IF EXISTS "Admin can insert skills" ON skills;
DROP POLICY IF EXISTS "Admin can update skills" ON skills;
DROP POLICY IF EXISTS "Admin can delete skills" ON skills;

DROP POLICY IF EXISTS "read_religions" ON religions;
DROP POLICY IF EXISTS "admin_religions" ON religions;
DROP POLICY IF EXISTS "Admin can insert religions" ON religions;
DROP POLICY IF EXISTS "Admin can update religions" ON religions;
DROP POLICY IF EXISTS "Admin can delete religions" ON religions;

DROP POLICY IF EXISTS "read_user_skills" ON user_skills;
DROP POLICY IF EXISTS "user_own_skills" ON user_skills;

DROP POLICY IF EXISTS "read_job_skills" ON job_skills;
DROP POLICY IF EXISTS "employer_job_skills" ON job_skills;

CREATE POLICY "read_skills" ON skills FOR SELECT USING (true);
CREATE POLICY "read_religions" ON religions FOR SELECT USING (true);
CREATE POLICY "read_user_skills" ON user_skills FOR SELECT USING (true);
CREATE POLICY "read_job_skills" ON job_skills FOR SELECT USING (true);

CREATE POLICY "admin_skills" ON skills FOR ALL
    USING (current_setting('request.jwt.claim.role', true) = 'admin');

CREATE POLICY "admin_religions" ON religions FOR ALL
    USING (current_setting('request.jwt.claim.role', true) = 'admin');

CREATE POLICY "user_own_skills" ON user_skills FOR ALL
    USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "employer_job_skills" ON job_skills FOR ALL
    USING (EXISTS (SELECT 1 FROM jobs WHERE id = job_id AND employer_id = current_setting('request.jwt.claim.user_id', true)::uuid));

-- 8j. invitations
DROP POLICY IF EXISTS "Employers can insert invitations" ON invitations;
DROP POLICY IF EXISTS "Users can read their invitations" ON invitations;
DROP POLICY IF EXISTS "Workers can update invitations" ON invitations;

CREATE POLICY "Employers can insert invitations" ON invitations
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

CREATE POLICY "Users can read their invitations" ON invitations
    FOR SELECT USING (current_setting('request.jwt.claim.user_id', true)::uuid = worker_id OR current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

CREATE POLICY "Workers can update invitations" ON invitations
    FOR UPDATE USING (current_setting('request.jwt.claim.user_id', true)::uuid = worker_id);

-- 8k. job_payments
DROP POLICY IF EXISTS "Employers can read own payments" ON job_payments;
DROP POLICY IF EXISTS "Service can insert payments" ON job_payments;
DROP POLICY IF EXISTS "Users can update own job payments" ON job_payments;

CREATE POLICY "Employers can read own payments" ON job_payments
    FOR SELECT USING (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

CREATE POLICY "Service can insert payments" ON job_payments
    FOR INSERT WITH CHECK (employer_id = current_setting('request.jwt.claim.user_id', true)::uuid);

CREATE POLICY "Users can update own job payments" ON job_payments
    FOR UPDATE USING (employer_id = current_setting('request.jwt.claim.user_id', true)::uuid);

-- 8l. tariff_settings
DROP POLICY IF EXISTS "Anyone can read tariff settings" ON tariff_settings;

CREATE POLICY "Anyone can read tariff settings" ON tariff_settings
    FOR SELECT USING (true);

-- 8m. monetization_settings
DROP POLICY IF EXISTS monetization_settings_select ON monetization_settings;
DROP POLICY IF EXISTS monetization_settings_insert ON monetization_settings;
DROP POLICY IF EXISTS monetization_settings_update ON monetization_settings;

CREATE POLICY monetization_settings_select ON monetization_settings
    FOR SELECT USING (true);

CREATE POLICY monetization_settings_insert ON monetization_settings
    FOR INSERT WITH CHECK (
        current_setting('request.jwt.claim.role', true) = 'admin'
    );

CREATE POLICY monetization_settings_update ON monetization_settings
    FOR UPDATE USING (
        current_setting('request.jwt.claim.role', true) = 'admin'
    );

-- 8n. _archive_contact_payments
DROP POLICY IF EXISTS contact_payments_select ON _archive_contact_payments;
DROP POLICY IF EXISTS contact_payments_insert ON _archive_contact_payments;
DROP POLICY IF EXISTS contact_payments_update ON _archive_contact_payments;

CREATE POLICY contact_payments_select ON _archive_contact_payments
    FOR SELECT USING (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id OR current_setting('request.jwt.claim.user_id', true)::uuid = worker_id);

CREATE POLICY contact_payments_insert ON _archive_contact_payments
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

CREATE POLICY contact_payments_update ON _archive_contact_payments
    FOR UPDATE USING (current_setting('request.jwt.claim.user_id', true)::uuid = employer_id);

-- 8o. receipts
DROP POLICY IF EXISTS receipts_select ON receipts;
DROP POLICY IF EXISTS receipts_insert ON receipts;
DROP POLICY IF EXISTS receipts_update ON receipts;

CREATE POLICY receipts_select ON receipts
    FOR SELECT USING (
        current_setting('request.jwt.claim.user_id', true)::uuid IN (
            SELECT employer_id FROM _archive_contact_payments WHERE _archive_contact_payments.id = receipts.contact_payment_id
            UNION
            SELECT worker_id FROM _archive_contact_payments WHERE _archive_contact_payments.id = receipts.contact_payment_id
        ) OR current_setting('request.jwt.claim.role', true) = 'admin'
    );

CREATE POLICY receipts_insert ON receipts
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.role', true) = 'admin');

CREATE POLICY receipts_update ON receipts
    FOR UPDATE USING (current_setting('request.jwt.claim.role', true) = 'admin');

-- 8p. push_subscriptions
DROP POLICY IF EXISTS "Users can view own push subscriptions" ON push_subscriptions;
DROP POLICY IF EXISTS "Users can create own push subscriptions" ON push_subscriptions;
DROP POLICY IF EXISTS "Users can delete own push subscriptions" ON push_subscriptions;
DROP POLICY IF EXISTS "Users can update own push subscriptions" ON push_subscriptions;
DROP POLICY IF EXISTS "Admins have full access to push_subscriptions" ON push_subscriptions;

CREATE POLICY "Users can view own push subscriptions" ON push_subscriptions
    FOR SELECT USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can create own push subscriptions" ON push_subscriptions
    FOR INSERT WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can update own push subscriptions" ON push_subscriptions
    FOR UPDATE USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id)
    WITH CHECK (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

CREATE POLICY "Users can delete own push subscriptions" ON push_subscriptions
    FOR DELETE USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- 8q. email_log
DROP POLICY IF EXISTS "Users can view own email logs" ON email_log;
DROP POLICY IF EXISTS "Service can insert email logs" ON email_log;
DROP POLICY IF EXISTS "Admins have full access to email_log" ON email_log;

CREATE POLICY "Service can insert email logs"
    ON email_log FOR INSERT WITH CHECK (true);

CREATE POLICY "Users can view own email logs" ON email_log
    FOR SELECT USING (current_setting('request.jwt.claim.user_id', true)::uuid = user_id);

-- 8r. spatial_ref_sys (PostGIS)
DO $$ BEGIN
    DROP POLICY IF EXISTS "spatial_ref_sys_select" ON public.spatial_ref_sys;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY "spatial_ref_sys_select"
        ON public.spatial_ref_sys
        FOR SELECT
        USING (true);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- ============================================
-- СЕКЦИЯ 9: RPC ФУНКЦИИ
-- ============================================

-- 9a. Три auth RPC (нативная аутентификация через pgcrypto)

-- RPC: логин (проверка пароля через pgcrypto)
CREATE OR REPLACE FUNCTION login_user(p_email text, p_password text)
RETURNS TABLE(user_id uuid, role text, full_name text) AS $$
BEGIN
    RETURN QUERY
    SELECT p.id, p.role, p.full_name
    FROM profiles p
    WHERE p.email = p_email
      AND p.password_hash = crypt(p_password, p.password_hash)
    LIMIT 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: регистрация
CREATE OR REPLACE FUNCTION register_user(
    p_email text, p_password text, p_full_name text, p_role text DEFAULT 'worker'
) RETURNS uuid AS $$
DECLARE
    v_user_id uuid;
BEGIN
    IF EXISTS (SELECT 1 FROM profiles WHERE email = p_email) THEN
        RAISE EXCEPTION 'email_exists';
    END IF;
    INSERT INTO profiles (id, email, password_hash, full_name, role)
    VALUES (gen_random_uuid(), p_email, crypt(p_password, gen_salt('bf')), p_full_name, p_role)
    RETURNING id INTO v_user_id;
    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- RPC: смена пароля
CREATE OR REPLACE FUNCTION change_password(
    p_user_id uuid, p_old_password text, p_new_password text
) RETURNS boolean AS $$
DECLARE
    v_hash text;
BEGIN
    SELECT password_hash INTO v_hash FROM profiles WHERE id = p_user_id;
    IF v_hash IS NULL OR v_hash != crypt(p_old_password, v_hash) THEN
        RETURN false;
    END IF;
    UPDATE profiles SET password_hash = crypt(p_new_password, gen_salt('bf')) WHERE id = p_user_id;
    RETURN true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 9b. exec_sql — безопасная RPC для скриптов (только service_role)
DO $$ BEGIN
    DROP FUNCTION IF EXISTS public.exec_sql(text) CASCADE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

CREATE OR REPLACE FUNCTION public.exec_sql(sql_query text)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    result JSONB;
BEGIN
    IF current_setting('role', true) != 'service_role' THEN
        RAISE EXCEPTION 'Только service_role может выполнять SQL-запросы через exec_sql';
    END IF;

    EXECUTE 'SELECT jsonb_agg(t) FROM (' || sql_query || ') t' INTO result;
    RETURN coalesce(result, '[]'::jsonb);
END;
$$;

-- 9c. accept_application — атомарное принятие отклика (rejected→accepted, версия из 064)
CREATE OR REPLACE FUNCTION accept_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_count int;
    v_new_status text;
    v_result json;
BEGIN
    SELECT current_workers, max_workers, status
    INTO v_current_workers, v_max_workers, v_job_status
    FROM jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object('success', false, 'error', 'Задание закрыто для принятия');
    END IF;

    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object('success', false, 'error', 'Все места заняты');
    END IF;

    v_new_count := v_current_workers + 1;
    v_new_status := CASE WHEN v_new_count >= v_max_workers THEN 'completed' ELSE 'open' END;

    UPDATE jobs
    SET status = v_new_status,
        current_workers = v_new_count
    WHERE id = p_job_id;

    UPDATE applications
    SET status = 'accepted'
    WHERE id = p_app_id AND job_id = p_job_id AND status IN ('pending', 'rejected');

    IF NOT FOUND THEN
        UPDATE jobs
        SET status = v_job_status,
            current_workers = v_current_workers
        WHERE id = p_job_id;
        RETURN json_build_object('success', false, 'error', 'Отклик не найден или уже обработан');
    END IF;

    UPDATE applications
    SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending' AND id != p_app_id;

    RETURN json_build_object(
        'success', true,
        'message', 'Отклик принят',
        'current_workers', v_new_count,
        'job_status', v_new_status
    );
END;
$$;

-- 9d. reject_application — отклонение отклика
CREATE OR REPLACE FUNCTION reject_application(
    p_job_id uuid,
    p_app_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_current_status text;
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_workers int;
    v_new_job_status text;
    v_result json;
BEGIN
    SELECT status INTO v_current_status
    FROM applications
    WHERE id = p_app_id AND job_id = p_job_id;

    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Отклик не найден');
    END IF;

    IF v_current_status = 'accepted' THEN
        SELECT current_workers, max_workers, status
        INTO v_current_workers, v_max_workers, v_job_status
        FROM jobs
        WHERE id = p_job_id
        FOR UPDATE;

        v_new_workers := GREATEST(0, v_current_workers - 1);
        v_new_job_status := CASE WHEN v_new_workers = 0 THEN 'open' ELSE 'completed' END;

        UPDATE jobs
        SET current_workers = v_new_workers,
            status = v_new_job_status
        WHERE id = p_job_id;

        UPDATE applications
        SET status = 'rejected'
        WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true,
            'new_status', 'rejected',
            'current_workers', v_new_workers,
            'job_status', v_new_job_status,
            'message', 'Работник отклонён'
        );
    ELSE
        UPDATE applications
        SET status = 'rejected'
        WHERE id = p_app_id;

        v_result := json_build_object(
            'success', true,
            'new_status', 'rejected',
            'message', 'Отклик отклонён'
        );
    END IF;

    RETURN v_result;
END;
$$;

-- 9e. delete_job_cascade — каскадное удаление задания
CREATE OR REPLACE FUNCTION delete_job_cascade(
    p_job_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_deleted_apps int;
    v_deleted_skills int;
    v_deleted_photos int;
    v_deleted_favorites int;
    v_deleted_invitations int;
    v_deleted_notifications int;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM jobs WHERE id = p_job_id) THEN
        RETURN json_build_object('success', false, 'error', 'Задание не найдено');
    END IF;

    DELETE FROM applications WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_apps = ROW_COUNT;

    DELETE FROM job_skills WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_skills = ROW_COUNT;

    DELETE FROM job_photos WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_photos = ROW_COUNT;

    DELETE FROM job_favorites WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_favorites = ROW_COUNT;

    DELETE FROM invitations WHERE job_id = p_job_id;
    GET DIAGNOSTICS v_deleted_invitations = ROW_COUNT;

    DELETE FROM notifications WHERE message ILIKE '%' || p_job_id::text || '%';
    GET DIAGNOSTICS v_deleted_notifications = ROW_COUNT;

    DELETE FROM jobs WHERE id = p_job_id;

    RETURN json_build_object(
        'success', true,
        'deleted', json_build_object(
            'applications', v_deleted_apps,
            'job_skills', v_deleted_skills,
            'job_photos', v_deleted_photos,
            'job_favorites', v_deleted_favorites,
            'invitations', v_deleted_invitations,
            'notifications', v_deleted_notifications
        ),
        'message', 'Задание удалено'
    );
END;
$$;

-- 9f. delete_user_cascade — каскадное удаление пользователя
CREATE OR REPLACE FUNCTION delete_user_cascade(
    p_user_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_role text;
BEGIN
    SELECT role INTO v_role FROM profiles WHERE id = p_user_id;
    IF NOT FOUND THEN
        RETURN json_build_object('success', false, 'error', 'Пользователь не найден');
    END IF;

    IF v_role = 'employer' THEN
        PERFORM delete_job_cascade(job.id)
        FROM (SELECT id FROM jobs WHERE employer_id = p_user_id) AS job;
    END IF;

    DELETE FROM applications WHERE worker_id = p_user_id;
    DELETE FROM notifications WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE user_id = p_user_id;
    DELETE FROM favorites WHERE target_id = p_user_id;
    DELETE FROM job_favorites WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE user_id = p_user_id;
    DELETE FROM blacklists WHERE blocked_user_id = p_user_id;
    DELETE FROM ratings WHERE rater_user_id = p_user_id;
    DELETE FROM ratings WHERE rated_user_id = p_user_id;
    DELETE FROM invitations WHERE employer_id = p_user_id;
    DELETE FROM invitations WHERE worker_id = p_user_id;
    DELETE FROM user_skills WHERE user_id = p_user_id;
    DELETE FROM push_subscriptions WHERE user_id = p_user_id;
    DELETE FROM messages WHERE sender_id = p_user_id;

    DELETE FROM profiles WHERE id = p_user_id;

    RETURN json_build_object(
        'success', true,
        'message', 'Пользователь удалён'
    );
END;
$$;

-- 9g. apply_job_atomic — атомарное создание отклика
CREATE OR REPLACE FUNCTION apply_job_atomic(
    p_job_id uuid,
    p_worker_id uuid
) RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_job_status text;
    v_current_workers int;
    v_max_workers int;
    v_employer_id uuid;
    v_blacklisted boolean;
    v_already_applied boolean;
BEGIN
    SELECT status, current_workers, max_workers, employer_id
    INTO v_job_status, v_current_workers, v_max_workers, v_employer_id
    FROM jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_job_status != 'open' THEN
        RETURN json_build_object(
            'success', false,
            'error', 'На это задание нельзя откликаться',
            'code', 'job_not_open'
        );
    END IF;

    IF v_employer_id = p_worker_id THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Вы не можете откликаться на собственное задание',
            'code', 'own_job'
        );
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM blacklists
        WHERE user_id = v_employer_id AND blocked_user_id = p_worker_id
    ) INTO v_blacklisted;

    IF v_blacklisted THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Вы не можете откликнуться: работодатель добавил вас в чёрный список',
            'code', 'blacklisted'
        );
    END IF;

    SELECT EXISTS(
        SELECT 1 FROM applications
        WHERE job_id = p_job_id AND worker_id = p_worker_id
    ) INTO v_already_applied;

    IF v_already_applied THEN
        RETURN json_build_object(
            'success', false,
            'error', 'Вы уже откликались на это задание',
            'code', 'duplicate'
        );
    END IF;

    IF v_current_workers >= v_max_workers THEN
        RETURN json_build_object(
            'success', false,
            'error', format('Места в задании заполнены (максимум %s)', v_max_workers),
            'code', 'no_slots'
        );
    END IF;

    INSERT INTO applications (job_id, worker_id, status)
    VALUES (p_job_id, p_worker_id, 'pending');

    RETURN json_build_object(
        'success', true,
        'message', 'Отклик отправлен',
        'employer_id', v_employer_id
    );
END;
$$;

-- 9h. get_job_stats — статистика заданий
CREATE OR REPLACE FUNCTION public.get_job_stats()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    _result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total', COUNT(*),
        'open', COUNT(*) FILTER (WHERE status = 'open'),
        'completed', COUNT(*) FILTER (WHERE status = 'completed'),
        'cancelled', COUNT(*) FILTER (WHERE status = 'cancelled')
    ) INTO _result
    FROM public.jobs;
    RETURN _result;
END;
$$;

-- 9i. nearby_jobs — поиск заданий по геолокации
CREATE OR REPLACE FUNCTION public.nearby_jobs(
    lat double precision,
    lng double precision,
    radius_km double precision DEFAULT 50
)
RETURNS SETOF jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
    _point geometry;
    _radius_meters double precision;
BEGIN
    _point := ST_SetSRID(ST_MakePoint(lng, lat), 4326);
    _radius_meters := radius_km * 1000;

    RETURN QUERY
    SELECT j.*
    FROM jobs j
    WHERE j.status = 'open'
      AND j.lat IS NOT NULL
      AND j.lng IS NOT NULL
      AND ST_DWithin(
            ST_SetSRID(ST_MakePoint(j.lng, j.lat), 4326)::geography,
            _point::geography,
            _radius_meters
          )
    ORDER BY
        ST_Distance(
            ST_SetSRID(ST_MakePoint(j.lng, j.lat), 4326)::geography,
            _point::geography
        );
END;
$$;

-- ============================================
-- СЕКЦИЯ 10: 8 АТОМАРНЫХ RPC (из 059 + 061)
-- ============================================

-- 10.1 withdraw_application_atomic
CREATE OR REPLACE FUNCTION public.withdraw_application_atomic(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_worker_id uuid;
    v_job_id uuid;
    v_status text;
BEGIN
    SELECT worker_id, job_id, status
    INTO v_worker_id, v_job_id, v_status
    FROM public.applications
    WHERE id = p_application_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Заявка не найдена',
            'code', 'application_not_found'
        );
    END IF;

    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не автор этой заявки',
            'code', 'not_owner'
        );
    END IF;

    IF v_status != 'pending' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя отозвать заявку в статусе ''%s''', v_status),
            'code', 'invalid_status'
        );
    END IF;

    UPDATE public.applications
    SET status = 'withdrawn'
    WHERE id = p_application_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Заявка отозвана',
        'new_status', 'withdrawn',
        'job_id', v_job_id
    );
END;
$$;

-- 10.2 cancel_worker_atomic
CREATE OR REPLACE FUNCTION public.cancel_worker_atomic(
    p_application_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_worker_id uuid;
    v_job_id uuid;
    v_app_status text;
    v_employer_id uuid;
    v_current_workers int;
    v_max_workers int;
    v_job_status text;
    v_new_workers int;
    v_new_job_status text;
    v_notification_id uuid;
BEGIN
    SELECT worker_id, job_id, status
    INTO v_worker_id, v_job_id, v_app_status
    FROM public.applications
    WHERE id = p_application_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Заявка не найдена',
            'code', 'application_not_found'
        );
    END IF;

    IF v_app_status != 'accepted' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя отменить исполнителя в статусе ''%s''', v_app_status),
            'code', 'invalid_status'
        );
    END IF;

    SELECT employer_id, current_workers, max_workers, status
    INTO v_employer_id, v_current_workers, v_max_workers, v_job_status
    FROM public.jobs
    WHERE id = v_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    UPDATE public.applications
    SET status = 'cancelled'
    WHERE id = p_application_id;

    v_new_workers := GREATEST(0, v_current_workers - 1);

    IF v_new_workers = 0 AND v_job_status IN ('completed', 'active', 'in_progress') THEN
        v_new_job_status := 'open';
    ELSE
        v_new_job_status := v_job_status;
    END IF;

    UPDATE public.jobs
    SET current_workers = v_new_workers,
        status = v_new_job_status
    WHERE id = v_job_id;

    INSERT INTO public.notifications (user_id, type, title, message, data, is_read)
    VALUES (
        v_worker_id,
        'worker_cancelled',
        'Заявка отменена',
        format('Работодатель отменил ваше участие в задании #%s', v_job_id),
        jsonb_build_object('job_id', v_job_id, 'application_id', p_application_id),
        false
    )
    RETURNING id INTO v_notification_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Исполнитель отменён',
        'new_status', 'cancelled',
        'current_workers', v_new_workers,
        'job_status', v_new_job_status,
        'notification_id', v_notification_id
    );
END;
$$;

-- 10.3 rate_user_atomic
CREATE OR REPLACE FUNCTION public.rate_user_atomic(
    p_job_id uuid,
    p_rater_user_id uuid,
    p_rated_user_id uuid,
    p_rating int,
    p_comment text DEFAULT '',
    p_rating_type text DEFAULT 'worker',
    p_target_type text DEFAULT 'worker'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_new_avg numeric(3,1);
    v_new_count int;
BEGIN
    IF p_rating < 1 OR p_rating > 5 THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Рейтинг должен быть от 1 до 5',
            'code', 'invalid_rating'
        );
    END IF;

    IF p_rater_user_id = p_rated_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Нельзя оценить самого себя',
            'code', 'self_rating'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = p_job_id AND status = 'completed'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оценить можно только завершённое задание',
            'code', 'job_not_completed'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE id = p_rated_user_id
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    INSERT INTO public.ratings (
        job_id,
        rater_user_id,
        rated_user_id,
        rating,
        comment,
        rating_type,
        target_type,
        created_at,
        updated_at
    ) VALUES (
        p_job_id,
        p_rater_user_id,
        p_rated_user_id,
        p_rating,
        p_comment,
        p_rating_type,
        p_target_type,
        now(),
        now()
    )
    ON CONFLICT (rater_user_id, job_id)
    DO UPDATE SET
        rating = EXCLUDED.rating,
        comment = EXCLUDED.comment,
        updated_at = now();

    SELECT
        COALESCE(ROUND(AVG(rating)::numeric, 1), 0),
        COUNT(*)::int
    INTO v_new_avg, v_new_count
    FROM public.ratings
    WHERE rated_user_id = p_rated_user_id;

    UPDATE public.profiles
    SET rating = v_new_avg,
        ratings_count = v_new_count
    WHERE id = p_rated_user_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Оценка сохранена',
        'new_avg_rating', v_new_avg,
        'new_ratings_count', v_new_count
    );
END;
$$;

-- 10.4 update_job_status_atomic
CREATE OR REPLACE FUNCTION public.update_job_status_atomic(
    p_job_id uuid,
    p_new_status text,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current_status text;
    v_employer_id uuid;
    v_allowed boolean;
BEGIN
    SELECT status, employer_id
    INTO v_current_status, v_employer_id
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    v_allowed := false;

    IF v_current_status = 'active' AND p_new_status IN ('in_progress', 'completed', 'cancelled') THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'in_progress' AND p_new_status IN ('completed', 'cancelled') THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'open' AND p_new_status = 'cancelled' THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'completed' AND p_new_status = 'open' THEN
        v_allowed := true;
    END IF;

    IF v_current_status = 'cancelled' AND p_new_status = 'open' THEN
        v_allowed := true;
    END IF;

    IF v_current_status = p_new_status THEN
        v_allowed := true;
    END IF;

    IF NOT v_allowed THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Недопустимый переход статуса: ''%s'' → ''%s''', v_current_status, p_new_status),
            'code', 'invalid_transition',
            'current_status', v_current_status
        );
    END IF;

    UPDATE public.jobs
    SET status = p_new_status,
        updated_at = now()
    WHERE id = p_job_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Статус задания обновлён',
        'old_status', v_current_status,
        'new_status', p_new_status
    );
END;
$$;

-- 10.5 resolve_user_atomic
CREATE OR REPLACE FUNCTION public.resolve_user_atomic(
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_profile record;
BEGIN
    SELECT id, full_name, photo_url, avatar_url, rating, role
    INTO v_profile
    FROM public.profiles
    WHERE id = p_user_id;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    RETURN jsonb_build_object(
        'success', true,
        'data', jsonb_build_object(
            'id', v_profile.id,
            'full_name', v_profile.full_name,
            'photo_url', COALESCE(v_profile.photo_url, v_profile.avatar_url, ''),
            'avatar_url', COALESCE(v_profile.avatar_url, v_profile.photo_url, ''),
            'rating', COALESCE(v_profile.rating, 0),
            'role', v_profile.role
        )
    );
END;
$$;

-- 10.6 cancel_job_atomic
CREATE OR REPLACE FUNCTION public.cancel_job_atomic(
    p_job_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_accepted_count int;
    v_rejected_workers uuid[];
BEGIN
    SELECT employer_id, status
    INTO v_employer_id, v_status
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    IF v_status = 'completed' THEN
        SELECT count(*) INTO v_accepted_count
        FROM public.applications
        WHERE job_id = p_job_id AND status = 'accepted';

        IF v_accepted_count > 0 THEN
            RETURN jsonb_build_object(
                'success', false,
                'error', 'Невозможно отменить задание с принятыми работниками. Сначала попросите работников отозвать отклики.',
                'code', 'has_accepted_workers',
                'accepted_count', v_accepted_count
            );
        END IF;
    END IF;

    UPDATE public.jobs
    SET status = 'cancelled',
        updated_at = now()
    WHERE id = p_job_id;

    WITH updated AS (
        UPDATE public.applications
        SET status = 'rejected'
        WHERE job_id = p_job_id AND status = 'pending'
        RETURNING worker_id
    )
    SELECT array_agg(DISTINCT worker_id)
    INTO v_rejected_workers
    FROM updated;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание отменено',
        'new_status', 'cancelled',
        'rejected_worker_ids', COALESCE(to_jsonb(v_rejected_workers), '[]'::jsonb)
    );
END;
$$;

-- 10.7 force_complete_job
CREATE OR REPLACE FUNCTION public.force_complete_job(
    p_job_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_employer_id uuid;
    v_status text;
    v_accepted_workers uuid[];
BEGIN
    SELECT employer_id, status
    INTO v_employer_id, v_status
    FROM public.jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_employer_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не владелец этого задания',
            'code', 'not_owner'
        );
    END IF;

    IF v_status != 'open' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Нельзя завершить задание в статусе ''%s''. Ожидается open.', v_status),
            'code', 'invalid_status',
            'current_status', v_status
        );
    END IF;

    UPDATE public.applications
    SET status = 'rejected'
    WHERE job_id = p_job_id AND status = 'pending';

    UPDATE public.jobs
    SET status = 'completed',
        updated_at = now()
    WHERE id = p_job_id;

    SELECT array_agg(DISTINCT worker_id)
    INTO v_accepted_workers
    FROM public.applications
    WHERE job_id = p_job_id AND status = 'accepted';

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Задание завершено',
        'new_status', 'completed',
        'accepted_worker_ids', COALESCE(to_jsonb(v_accepted_workers), '[]'::jsonb)
    );
END;
$$;

-- 10.8 accept_invitation_atomic
CREATE OR REPLACE FUNCTION public.accept_invitation_atomic(
    p_invitation_id uuid,
    p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_job_id uuid;
    v_employer_id uuid;
    v_worker_id uuid;
    v_inv_status text;
    v_job_status text;
    v_current_workers int;
    v_max_workers int;
    v_new_count int;
    v_new_job_status text;
    v_application_id uuid;
BEGIN
    SELECT job_id, employer_id, worker_id, status
    INTO v_job_id, v_employer_id, v_worker_id, v_inv_status
    FROM public.invitations
    WHERE id = p_invitation_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Приглашение не найдено',
            'code', 'invitation_not_found'
        );
    END IF;

    IF v_worker_id != p_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Это приглашение адресовано другому пользователю',
            'code', 'not_target'
        );
    END IF;

    IF v_inv_status != 'pending' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Приглашение уже %s', v_inv_status),
            'code', 'invitation_not_pending'
        );
    END IF;

    SELECT status, current_workers, max_workers
    INTO v_job_status, v_current_workers, v_max_workers
    FROM public.jobs
    WHERE id = v_job_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Задание не найдено',
            'code', 'job_not_found'
        );
    END IF;

    IF v_job_status != 'open' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Задание в статусе ''%s'' — нельзя принять приглашение', v_job_status),
            'code', 'job_not_open'
        );
    END IF;

    IF v_current_workers >= v_max_workers THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', format('Все места заняты (%s из %s)', v_current_workers, v_max_workers),
            'code', 'no_slots'
        );
    END IF;

    INSERT INTO public.applications (job_id, worker_id, status)
    VALUES (v_job_id, v_worker_id, 'accepted')
    ON CONFLICT (job_id, worker_id) DO UPDATE
        SET status = 'accepted'
    RETURNING id INTO v_application_id;

    v_new_count := v_current_workers + 1;
    IF v_new_count >= v_max_workers THEN
        v_new_job_status := 'completed';
    ELSE
        v_new_job_status := v_job_status;
    END IF;

    UPDATE public.jobs
    SET current_workers = v_new_count,
        status = v_new_job_status,
        updated_at = now()
    WHERE id = v_job_id;

    UPDATE public.invitations
    SET status = 'accepted',
        responded_at = now()
    WHERE id = p_invitation_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Приглашение принято',
        'job_id', v_job_id,
        'employer_id', v_employer_id,
        'worker_id', v_worker_id,
        'application_id', v_application_id,
        'current_workers', v_new_count,
        'job_status', v_new_job_status
    );
END;
$$;

-- ============================================
-- СЕКЦИЯ 11: ПРАВА ДОСТУПА (REVOKE/GRANT)
-- ============================================

-- Auth RPC
-- login_user — доступен всем (включая anon)
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO anon, authenticated, service_role;

-- register_user — доступен всем (включая anon)
REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO anon, authenticated, service_role;

-- change_password — только для authenticated
REVOKE EXECUTE ON FUNCTION change_password(uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION change_password(uuid, text, text) TO authenticated, service_role;

-- exec_sql
REVOKE EXECUTE ON FUNCTION public.exec_sql(text) FROM anon, authenticated, PUBLIC;
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;

-- accept_application / reject_application
REVOKE EXECUTE ON FUNCTION public.accept_application(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_application(uuid, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.reject_application(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.reject_application(uuid, uuid) TO authenticated, service_role;

-- apply_job_atomic
REVOKE EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.apply_job_atomic(uuid, uuid) TO authenticated, service_role;

-- delete_user_cascade / delete_job_cascade
REVOKE EXECUTE ON FUNCTION public.delete_user_cascade(uuid) FROM anon, authenticated, PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_user_cascade(uuid) TO service_role;

REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM anon, authenticated, PUBLIC;
GRANT EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO service_role;

-- get_job_stats
GRANT EXECUTE ON FUNCTION public.get_job_stats() TO service_role;
REVOKE EXECUTE ON FUNCTION public.get_job_stats() FROM anon, authenticated, PUBLIC;

-- nearby_jobs
GRANT EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) TO authenticated;
REVOKE EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) FROM anon, PUBLIC;

-- Атомарные RPC (059)
REVOKE EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.withdraw_application_atomic(uuid, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_worker_atomic(uuid, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.update_job_status_atomic(uuid, text, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.update_job_status_atomic(uuid, text, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.resolve_user_atomic(uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.resolve_user_atomic(uuid) TO authenticated, service_role;

-- Атомарные RPC (061)
REVOKE EXECUTE ON FUNCTION public.cancel_job_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.cancel_job_atomic(uuid, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.force_complete_job(uuid, uuid) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.accept_invitation_atomic(uuid, uuid) TO authenticated, service_role;

-- GRANT для service_role на справочные таблицы
GRANT SELECT, INSERT, UPDATE, DELETE ON public.skills TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.religions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_skills TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.job_skills TO service_role;

-- GRANT для service_role на monetization/settings таблицы
GRANT SELECT, INSERT, UPDATE, DELETE ON monetization_settings TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON receipts TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON _archive_contact_payments TO service_role;

-- Отзыв прав на st_estimatedextent (PostGIS) у anon/authenticated
DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text) FROM anon, authenticated, PUBLIC;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text) FROM anon, authenticated, PUBLIC;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$ BEGIN
    REVOKE EXECUTE ON FUNCTION public.st_estimatedextent(text, text, text, boolean) FROM anon, authenticated, PUBLIC;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Дроп устаревших функций и таблиц (легаси)
DO $$ BEGIN
    DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$ BEGIN
    DROP FUNCTION IF EXISTS public.execute_sql CASCADE;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DROP TABLE IF EXISTS reviews CASCADE;
DROP TABLE IF EXISTS hires CASCADE;
DROP TABLE IF EXISTS shifts CASCADE;

-- ============================================
-- СЕКЦИЯ 12: СОЗДАНИЕ АДМИНИСТРАТОРА
-- ============================================

INSERT INTO profiles (id, email, password_hash, full_name, role, created_at)
VALUES (
    gen_random_uuid(),
    'admin@test.ru',
    crypt('Step@1986', gen_salt('bf')),
    'Администратор',
    'admin',
    now()
)
ON CONFLICT (email) DO UPDATE SET
    password_hash = crypt('Step@1986', gen_salt('bf')),
    role = 'admin';

-- ============================================================================
-- ГОТОВО!
-- 
-- Итого в этом скрипте:
--   3 расширения (pgcrypto, postgis, pg_trgm)
--   3 роли (anon, authenticated, service_role)
--   24 таблицы (все колонки, constraints, FK)
--   Seed-данные (20 навыков, 6 религий, тариф, монетизация)
--   ~40 индексов
--   2 поисковых триггера (jobs, profiles)
--   RLS включён на 22 таблицах
--   ~70 RLS-политик
--   14 RPC-функций:
--     - 3 auth (login_user, register_user, change_password)
--     - exec_sql, accept_application, reject_application
--     - delete_job_cascade, delete_user_cascade
--     - apply_job_atomic, get_job_stats, nearby_jobs
--     - 8 атомарных (withdraw, cancel_worker, rate_user,
--       update_job_status, resolve_user, cancel_job,
--       force_complete_job, accept_invitation)
--   Все REVOKE/GRANT
--   Администратор admin@test.ru / Step@1986
-- ============================================================================
