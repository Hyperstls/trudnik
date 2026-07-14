-- Migration 122: Fix notification_outbox RLS policy
--
-- Problem (v1): Table notification_outbox was created in migration 075
-- without GRANT statements. PostgREST (connected as trudnikapp) cannot
-- SELECT/INSERT/UPDATE/DELETE, causing 403 Forbidden in drain_notification_outbox.
--
-- Problem (v2): The original policy used "FOR ALL TO service_role", but
-- service_role is NOT a real PostgreSQL role — it only exists as a JWT claim.
-- PostgREST connects as trudnikapp, so current_user is always trudnikapp,
-- and "TO service_role" never matches → 403 Forbidden on every drain.
--
-- Fix: Use current_setting('request.jwt.claim.role') check instead of TO,
-- matching the style of all other RLS policies in the codebase.
--
-- This migration is idempotent (GRANT is safe to re-run, DROP+CREATE policy).

-- Grant access to authenticated role (for user-facing operations via PostgREST)
GRANT SELECT, INSERT, UPDATE, DELETE ON notification_outbox TO authenticated;

-- Grant access to service_role (for Celery background tasks / admin operations)
GRANT SELECT, INSERT, UPDATE, DELETE ON notification_outbox TO service_role;

-- Grant sequence usage for BIGSERIAL id column
GRANT USAGE, SELECT ON SEQUENCE notification_outbox_id_seq TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE notification_outbox_id_seq TO service_role;

-- Enable RLS but allow service_role (JWT claim) to bypass
-- notification_outbox is a system table managed by Celery, so we only
-- allow access when the JWT claim role is 'service_role'.
ALTER TABLE notification_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_outbox FORCE ROW LEVEL SECURITY;

-- Policy: service_role (JWT claim) has full access
DROP POLICY IF EXISTS outbox_service_all ON notification_outbox;
CREATE POLICY outbox_service_all ON notification_outbox
    FOR ALL
    USING (current_setting('request.jwt.claim.role', true) = 'service_role')
    WITH CHECK (current_setting('request.jwt.claim.role', true) = 'service_role');
