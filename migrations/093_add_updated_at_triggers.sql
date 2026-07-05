-- 093_add_updated_at_triggers.sql
-- Автообновление updated_at при UPDATE для ключевых таблиц.
-- Обеспечивает консистентность временных меток на уровне БД.

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- profiles
DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- jobs
DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- applications
DROP TRIGGER IF EXISTS trg_applications_updated_at ON applications;
CREATE TRIGGER trg_applications_updated_at
    BEFORE UPDATE ON applications
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- employer_subscriptions
DROP TRIGGER IF EXISTS trg_employer_subscriptions_updated_at ON employer_subscriptions;
CREATE TRIGGER trg_employer_subscriptions_updated_at
    BEFORE UPDATE ON employer_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
