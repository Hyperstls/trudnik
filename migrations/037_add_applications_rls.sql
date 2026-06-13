-- Миграция 037: RLS-политики DELETE и UPDATE для applications
BEGIN;

-- Пользователь может удалить/отозвать свой отклик
CREATE POLICY "Users can delete own applications" ON applications
    FOR DELETE USING ((SELECT auth.uid()) = worker_id);

-- Пользователь может обновить свой отклик
CREATE POLICY "Users can update own applications" ON applications
    FOR UPDATE USING ((SELECT auth.uid()) = worker_id)
    WITH CHECK ((SELECT auth.uid()) = worker_id);

-- Работодатель может обновить статус отклика на своё задание
CREATE POLICY "Employers can update applications on their jobs" ON applications
    FOR UPDATE USING (
        EXISTS (SELECT 1 FROM jobs WHERE jobs.id = applications.job_id AND jobs.employer_id = (SELECT auth.uid()))
    );

COMMIT;
