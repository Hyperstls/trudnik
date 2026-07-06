-- Migration 122: Fix notification_outbox GRANT permissions
--
-- Problem: Table notification_outbox was created in migration 075
-- without GRANT statements. PostgREST (connected as trudnikapp) cannot
-- SELECT/INSERT/UPDATE/DELETE, causing 403 Forbidden in drain_notification_outbox.
--
-- This migration is idempotent (GRANT is safe to re-run).

-- Grant access to authenticated role (for user-facing operations via PostgREST)
GRANT SELECT, INSERT, UPDATE, DELETE ON notification_outbox TO authenticated;

-- Grant access to service_role (for Celery background tasks / admin operations)
GRANT SELECT, INSERT, UPDATE, DELETE ON notification_outbox TO service_role;

-- Grant sequence usage for BIGSERIAL id column
GRANT USAGE, SELECT ON SEQUENCE notification_outbox_id_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE notification_outbox_id_seq TO service_role;

-- Enable RLS but allow service_role to bypass (BYPASSRLS is set on role)
-- notification_outbox is a system table managed by Celery, so we don't
-- need per-user RLS policies — service_role handles all access.
ALTER TABLE notification_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_outbox FORCE ROW LEVEL SECURITY;

-- Policy: service_role has full access
DROP POLICY IF EXISTS outbox_service_all ON notification_outbox;
CREATE POLICY outbox_service_all ON notification_outbox
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);
