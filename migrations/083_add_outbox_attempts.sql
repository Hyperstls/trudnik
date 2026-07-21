ALTER TABLE notification_outbox ADD COLUMN IF NOT EXISTS attempts INT DEFAULT 0;
ALTER TABLE notification_outbox DROP CONSTRAINT IF EXISTS notification_outbox_status_check;
ALTER TABLE notification_outbox ADD CONSTRAINT notification_outbox_status_check 
    CHECK (status IN ('pending','sent','failed','skipped'));
