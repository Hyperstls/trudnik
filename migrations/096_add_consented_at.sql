-- 096: Добавление поля consented_at в profiles (152-ФЗ — согласие с условиями)
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS consented_at TIMESTAMPTZ;
