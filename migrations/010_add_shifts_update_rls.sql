-- Добавление RLS-политики UPDATE для таблицы shifts
-- Работник может обновлять свою смену (checkin, complete)
-- Работодатель может обновлять свою смену (confirm_payment)
-- Выполнить в Supabase SQL Editor

ALTER TABLE shifts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can update their own shifts" ON shifts;

CREATE POLICY "Users can update their own shifts"
    ON shifts
    FOR UPDATE
    USING (
        auth.uid() = worker_id OR auth.uid() = employer_id
    )
    WITH CHECK (
        auth.uid() = worker_id OR auth.uid() = employer_id
    );

-- Добавляем 'completed' и 'cancelled' в RLS SELECT для jobs
DROP POLICY IF EXISTS "Users can read jobs" ON jobs;
CREATE POLICY "Users can read jobs"
    ON jobs
    FOR SELECT
    USING (
        status IN ('open', 'in_progress', 'active', 'payment_pending', 'completed', 'cancelled')
    );
