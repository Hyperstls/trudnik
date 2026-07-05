-- Перенести зависимости с дубликатов на "выжившие" профили
DO $$
DECLARE
    dup RECORD;
    keep_id uuid;
BEGIN
    FOR dup IN
        SELECT LOWER(email) AS le, (array_agg(id ORDER BY created_at ASC))[1] AS keep_id
        FROM profiles GROUP BY LOWER(email) HAVING COUNT(*) > 1
    LOOP
        keep_id := dup.keep_id;
        
        UPDATE applications SET worker_id = keep_id
        WHERE worker_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE jobs SET employer_id = keep_id
        WHERE employer_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE ratings SET rater_user_id = keep_id
        WHERE rater_user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE ratings SET rated_user_id = keep_id
        WHERE rated_user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE notifications SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE favorites SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE favorites SET target_id = keep_id
        WHERE target_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE blacklists SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE blacklists SET blocked_user_id = keep_id
        WHERE blocked_user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE messages SET sender_id = keep_id
        WHERE sender_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE push_subscriptions SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE user_skills SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE invitations SET employer_id = keep_id
        WHERE employer_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE invitations SET worker_id = keep_id
        WHERE worker_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        UPDATE audit_log SET user_id = keep_id
        WHERE user_id IN (SELECT id FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id);
        
        -- Удалить дубликаты
        DELETE FROM profiles WHERE LOWER(email) = dup.le AND id != keep_id;
    END LOOP;
END $$;

-- Привести к нижнему регистру
UPDATE profiles SET email = LOWER(email) WHERE email != LOWER(email);

-- Case-insensitive индекс
DROP INDEX IF EXISTS idx_profiles_email;
CREATE UNIQUE INDEX idx_profiles_email ON profiles(LOWER(email));
