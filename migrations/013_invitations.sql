-- Таблица приглашений: работодатель приглашает трудника на задание
CREATE TABLE IF NOT EXISTS invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE NOT NULL,
    employer_id UUID REFERENCES auth.users(id) NOT NULL,
    worker_id UUID REFERENCES auth.users(id) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    UNIQUE(job_id, worker_id)
);

CREATE INDEX IF NOT EXISTS idx_invitations_worker ON invitations(worker_id);
CREATE INDEX IF NOT EXISTS idx_invitations_employer ON invitations(employer_id);
CREATE INDEX IF NOT EXISTS idx_invitations_job ON invitations(job_id);

-- RLS
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Employers can insert invitations" ON invitations;
CREATE POLICY "Employers can insert invitations" ON invitations
    FOR INSERT WITH CHECK (auth.uid() = employer_id);

DROP POLICY IF EXISTS "Users can read their invitations" ON invitations;
CREATE POLICY "Users can read their invitations" ON invitations
    FOR SELECT USING (auth.uid() = worker_id OR auth.uid() = employer_id);

DROP POLICY IF EXISTS "Workers can update invitations" ON invitations;
CREATE POLICY "Workers can update invitations" ON invitations
    FOR UPDATE USING (auth.uid() = worker_id);
