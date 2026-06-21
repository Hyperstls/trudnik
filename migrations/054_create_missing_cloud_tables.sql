-- ============================================================================
-- Миграция 054: Создание таблиц, отсутствующих в локальной схеме
-- Дата: 2026-06-21
-- Контекст: В облачном Supabase присутствуют таблицы monetization_settings,
--   receipts и _archive_contact_payments, которых нет в локальной схеме.
-- Идемпотентна: все операции с IF NOT EXISTS.
-- ============================================================================

-- ============================================================================
-- ШАГ 1: monetization_settings — настройки монетизации
-- ============================================================================

CREATE TABLE IF NOT EXISTS monetization_settings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key text NOT NULL,
    value text NOT NULL DEFAULT '',
    updated_at timestamptz DEFAULT now()
);

-- Базовые RLS: чтение — всем, запись — только админам
ALTER TABLE monetization_settings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'monetization_settings'
          AND policyname = 'monetization_settings_select'
    ) THEN
        CREATE POLICY monetization_settings_select ON monetization_settings
            FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'monetization_settings'
          AND policyname = 'monetization_settings_insert'
    ) THEN
        CREATE POLICY monetization_settings_insert ON monetization_settings
            FOR INSERT WITH CHECK (
                EXISTS (
                    SELECT 1 FROM profiles
                    WHERE profiles.id = auth.uid()
                      AND profiles.role = 'admin'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'monetization_settings'
          AND policyname = 'monetization_settings_update'
    ) THEN
        CREATE POLICY monetization_settings_update ON monetization_settings
            FOR UPDATE USING (
                EXISTS (
                    SELECT 1 FROM profiles
                    WHERE profiles.id = auth.uid()
                      AND profiles.role = 'admin'
                )
            );
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON monetization_settings TO service_role;

-- ============================================================================
-- ШАГ 2: receipts — чеки об оплате
-- ============================================================================

CREATE TABLE IF NOT EXISTS receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_payment_id uuid,
    church_name text NOT NULL DEFAULT '',
    church_inn text NOT NULL DEFAULT '',
    service_description text NOT NULL DEFAULT '',
    amount integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'sent',
    receipt_json jsonb DEFAULT '{}',
    created_at timestamptz DEFAULT now(),
    resent_at timestamptz
);

-- RLS: чтение — участники платежа или админ, запись — только админ
ALTER TABLE receipts ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'receipts'
          AND policyname = 'receipts_select'
    ) THEN
        CREATE POLICY receipts_select ON receipts
            FOR SELECT USING (
                auth.uid() IN (
                    SELECT employer_id FROM _archive_contact_payments
                    WHERE _archive_contact_payments.id = receipts.contact_payment_id
                    UNION
                    SELECT worker_id FROM _archive_contact_payments
                    WHERE _archive_contact_payments.id = receipts.contact_payment_id
                )
                OR EXISTS (
                    SELECT 1 FROM profiles
                    WHERE profiles.id = auth.uid()
                      AND profiles.role = 'admin'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'receipts'
          AND policyname = 'receipts_insert'
    ) THEN
        CREATE POLICY receipts_insert ON receipts
            FOR INSERT WITH CHECK (
                EXISTS (
                    SELECT 1 FROM profiles
                    WHERE profiles.id = auth.uid()
                      AND profiles.role = 'admin'
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'receipts'
          AND policyname = 'receipts_update'
    ) THEN
        CREATE POLICY receipts_update ON receipts
            FOR UPDATE USING (
                EXISTS (
                    SELECT 1 FROM profiles
                    WHERE profiles.id = auth.uid()
                      AND profiles.role = 'admin'
                )
            );
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON receipts TO service_role;

-- ============================================================================
-- ШАГ 3: _archive_contact_payments — архив платежей за контакты
-- ============================================================================

CREATE TABLE IF NOT EXISTS _archive_contact_payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id uuid NOT NULL,
    worker_id uuid NOT NULL,
    job_id uuid NOT NULL,
    application_id uuid,
    amount integer NOT NULL DEFAULT 290,
    status text NOT NULL DEFAULT 'pending',
    transaction_id text DEFAULT '',
    created_at timestamptz DEFAULT now(),
    paid_at timestamptz
);

-- RLS: чтение — только участники, запись — работодатель
ALTER TABLE _archive_contact_payments ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = '_archive_contact_payments'
          AND policyname = 'contact_payments_select'
    ) THEN
        CREATE POLICY contact_payments_select ON _archive_contact_payments
            FOR SELECT USING (
                auth.uid() = employer_id OR auth.uid() = worker_id
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = '_archive_contact_payments'
          AND policyname = 'contact_payments_insert'
    ) THEN
        CREATE POLICY contact_payments_insert ON _archive_contact_payments
            FOR INSERT WITH CHECK (auth.uid() = employer_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = '_archive_contact_payments'
          AND policyname = 'contact_payments_update'
    ) THEN
        CREATE POLICY contact_payments_update ON _archive_contact_payments
            FOR UPDATE USING (auth.uid() = employer_id);
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON _archive_contact_payments TO service_role;

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
