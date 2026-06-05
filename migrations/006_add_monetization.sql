-- ============================================================
-- Миграция 006: Монетизация и юридическая защита
-- Добавляет таблицы: monetization_settings, contact_payments,
-- receipts, hires. Добавляет поля в profiles и applications.
-- ============================================================

-- 1. Настройки монетизации (ключ-значение)
CREATE TABLE IF NOT EXISTS public.monetization_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Настройки по умолчанию
INSERT INTO public.monetization_settings (key, value) VALUES
    ('contact_price', '290'),
    ('owner_inn', '')
ON CONFLICT (key) DO NOTHING;

-- 2. Платежи за раскрытие контакта
CREATE TABLE IF NOT EXISTS public.contact_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    worker_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    amount INTEGER NOT NULL DEFAULT 290,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'refunded')),
    transaction_id TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT now(),
    paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_contact_payments_employer ON public.contact_payments(employer_id);
CREATE INDEX IF NOT EXISTS idx_contact_payments_worker ON public.contact_payments(worker_id);
CREATE INDEX IF NOT EXISTS idx_contact_payments_job ON public.contact_payments(job_id);

-- 3. Чеки самозанятого
CREATE TABLE IF NOT EXISTS public.receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_payment_id UUID REFERENCES public.contact_payments(id) ON DELETE SET NULL,
    church_name TEXT NOT NULL DEFAULT '',
    church_inn TEXT NOT NULL DEFAULT '',
    service_description TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'failed', 'resent')),
    receipt_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    resent_at TIMESTAMPTZ
);

-- 4. История наймов (для триггера переквалификации)
CREATE TABLE IF NOT EXISTS public.hires (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    worker_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    shift_id UUID REFERENCES public.shifts(id) ON DELETE SET NULL,
    hired_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_hires_pair ON public.hires(employer_id, worker_id);
CREATE INDEX IF NOT EXISTS idx_hires_date ON public.hires(hired_at);

ALTER TABLE public.hires ADD CONSTRAINT unique_hires_pair UNIQUE (employer_id, worker_id, job_id);

-- 5. Новые поля в profiles
ALTER TABLE public.profiles
    ADD COLUMN IF NOT EXISTS inn TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS is_self_employed BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS email_public TEXT DEFAULT '';

-- 6. Новые поля в applications
ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS contact_paid BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS contact_payment_id UUID REFERENCES public.contact_payments(id) ON DELETE SET NULL;

-- 7. RLS-политики для новых таблиц
ALTER TABLE public.monetization_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hires ENABLE ROW LEVEL SECURITY;

-- monetization_settings: читать могут все, писать только админ
CREATE POLICY monetization_settings_select ON public.monetization_settings
    FOR SELECT USING (true);

CREATE POLICY monetization_settings_insert ON public.monetization_settings
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

CREATE POLICY monetization_settings_update ON public.monetization_settings
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- contact_payments: читают employer и worker, создаёт employer
CREATE POLICY contact_payments_select ON public.contact_payments
    FOR SELECT USING (
        auth.uid() = employer_id OR auth.uid() = worker_id OR
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

CREATE POLICY contact_payments_insert ON public.contact_payments
    FOR INSERT WITH CHECK (auth.uid() = employer_id);

CREATE POLICY contact_payments_update ON public.contact_payments
    FOR UPDATE USING (
        auth.uid() = employer_id OR
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- receipts: читают участники и админ
CREATE POLICY receipts_select ON public.receipts
    FOR SELECT USING (
        auth.uid() IN (
            SELECT employer_id FROM public.contact_payments WHERE id = contact_payment_id
            UNION
            SELECT worker_id FROM public.contact_payments WHERE id = contact_payment_id
        ) OR EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

CREATE POLICY receipts_insert ON public.receipts
    FOR INSERT WITH CHECK (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

CREATE POLICY receipts_update ON public.receipts
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

-- hires: читают участники и админ
CREATE POLICY hires_select ON public.hires
    FOR SELECT USING (
        auth.uid() = employer_id OR auth.uid() = worker_id OR
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );

CREATE POLICY hires_insert ON public.hires
    FOR INSERT WITH CHECK (
        auth.uid() = employer_id OR
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin')
    );
