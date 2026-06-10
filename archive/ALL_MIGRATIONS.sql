-- ============================================
-- КРИТИЧЕСКИЕ МИГРАЦИИ ДЛЯ TRUDNIK
-- Скопируй всё и вставь в Supabase SQL Editor:
-- https://supabase.com/dashboard/project/***REMOVED***/sql/new
-- Нажми Run (Ctrl+Enter)
-- ============================================

-- 1. Счётчик занятых мест
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS max_workers INTEGER DEFAULT 1 CHECK (max_workers >= 1);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_workers INTEGER DEFAULT 0;
UPDATE jobs SET max_workers = 1 WHERE max_workers IS NULL;
UPDATE jobs SET current_workers = 0 WHERE current_workers IS NULL;

-- 2. RLS UPDATE для shifts
ALTER TABLE shifts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can update their own shifts" ON shifts;
CREATE POLICY "Users can update their own shifts" ON shifts FOR UPDATE
    USING (auth.uid() = worker_id OR auth.uid() = employer_id)
    WITH CHECK (auth.uid() = worker_id OR auth.uid() = employer_id);

-- 3. completed/cancelled в поиске заданий
DROP POLICY IF EXISTS "Users can read jobs" ON jobs;
CREATE POLICY "Users can read jobs" ON jobs FOR SELECT
    USING (status IN ('open','in_progress','active','payment_pending','completed','cancelled'));

-- 4. Уведомления
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS data JSONB DEFAULT '{}'::jsonb;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{}'::jsonb;

-- 5. Приглашения
CREATE TABLE IF NOT EXISTS invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE NOT NULL,
    employer_id UUID REFERENCES auth.users(id) NOT NULL,
    worker_id UUID REFERENCES auth.users(id) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
    message TEXT, created_at TIMESTAMPTZ DEFAULT NOW(), responded_at TIMESTAMPTZ,
    UNIQUE(job_id, worker_id)
);
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Employers can insert invitations" ON invitations;
CREATE POLICY "Employers can insert invitations" ON invitations FOR INSERT WITH CHECK (auth.uid() = employer_id);
DROP POLICY IF EXISTS "Users can read their invitations" ON invitations;
CREATE POLICY "Users can read their invitations" ON invitations FOR SELECT USING (auth.uid() = worker_id OR auth.uid() = employer_id);
DROP POLICY IF EXISTS "Workers can update invitations" ON invitations;
CREATE POLICY "Workers can update invitations" ON invitations FOR UPDATE USING (auth.uid() = worker_id);

-- 6. Контакт
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS contact TEXT;
