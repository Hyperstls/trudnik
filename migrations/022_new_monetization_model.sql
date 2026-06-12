-- ============================================================================
-- Миграция: Новая модель монетизации «Плата за публикацию задания»
-- Заменяет модель «pay-per-contact» на «pay-per-job»
-- Актуально на: 12.06.2026
-- ============================================================================

-- 1. Расширение таблицы jobs
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS tariff VARCHAR(20) DEFAULT 'standard';

-- 2. Новые статусы (draft, expired)
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_status_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_status_check 
    CHECK (status IN ('draft', 'open', 'in_progress', 'completed', 'cancelled', 'paid', 'expired'));

-- 3. Таблица job_payments (платежи за публикацию/продление)
CREATE TABLE IF NOT EXISTS job_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE NOT NULL,
    employer_id UUID REFERENCES auth.users(id) NOT NULL,
    amount INTEGER NOT NULL,
    tariff VARCHAR(20) DEFAULT 'standard',
    type VARCHAR(30) DEFAULT 'publication',
    status VARCHAR(20) DEFAULT 'pending',
    transaction_id VARCHAR(255),
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Таблица tariff_settings (настройки тарифов)
CREATE TABLE IF NOT EXISTS tariff_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tariff_key VARCHAR(30) UNIQUE NOT NULL,
    price INTEGER NOT NULL,
    duration_days INTEGER NOT NULL DEFAULT 30,
    renewal_price INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Заполнение дефолтным тарифом
INSERT INTO tariff_settings (tariff_key, price, duration_days, renewal_price)
VALUES ('standard', 490, 30, 290)
ON CONFLICT (tariff_key) DO NOTHING;

-- 5. Архивация старой таблицы contact_payments
ALTER TABLE IF EXISTS contact_payments RENAME TO _archive_contact_payments;

-- 6. Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_jobs_expires ON jobs(expires_at) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_job_payments_job ON job_payments(job_id);
CREATE INDEX IF NOT EXISTS idx_job_payments_employer ON job_payments(employer_id);

-- 7. RLS для новых таблиц
ALTER TABLE job_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE tariff_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Employers can read own payments" ON job_payments;
CREATE POLICY "Employers can read own payments" ON job_payments
    FOR SELECT USING (auth.uid() = employer_id);

DROP POLICY IF EXISTS "Service can insert payments" ON job_payments;
CREATE POLICY "Service can insert payments" ON job_payments
    FOR INSERT WITH CHECK (true);

-- Чтение тарифов доступно всем
DROP POLICY IF EXISTS "Anyone can read tariff settings" ON tariff_settings;
CREATE POLICY "Anyone can read tariff settings" ON tariff_settings
    FOR SELECT USING (true);

-- 8. Апдейт существующих open-заданий (проставить is_paid=true, expires_at=now+30d)
UPDATE jobs
SET is_paid = TRUE,
    expires_at = NOW() + INTERVAL '30 days',
    tariff = 'standard'
WHERE status = 'open' AND is_paid = FALSE;
