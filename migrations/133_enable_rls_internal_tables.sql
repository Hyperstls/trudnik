-- ============================================================================
-- Migration 133: Enable RLS on internal/admin tables (block anon reads)
-- ============================================================================
-- PROBLEM (P1, audit): these tables had RLS DISABLED (relrowsecurity=f) yet
--   migration 123 grants table-level SELECT to anon. anon could read:
--     - audit_log            (admin activity, user ids, actions)
--     - employer_subscriptions (tariff, billing)
--     - _migrations / schema_migrations (migration history)
--   Empty locally only because the tables were empty — any data = full leak.
--
-- FIX: ENABLE RLS + SELECT policies that exclude anon (no policy TO anon =>
--   RLS deny-default). service_role (BYPASSRLS) keeps full access.
--   - audit_log: admin-only (app_role=admin) + service_role
--   - employer_subscriptions: self-row (employer_id = jwt user_id) + service_role
--   - _migrations / schema_migrations: service_role only
--   Survives 123's table-level re-GRANT (RLS filters regardless of column grant).
--
-- Idempotent.
-- ============================================================================

BEGIN;

-- audit_log
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_log_select ON public.audit_log;
CREATE POLICY audit_log_select ON public.audit_log
    FOR SELECT TO authenticated, service_role
    USING (current_setting('request.jwt.claims', true)::json->>'app_role' = 'admin');

-- employer_subscriptions (employer reads own tariff via authenticated JWT)
ALTER TABLE public.employer_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS employer_subscriptions_select ON public.employer_subscriptions;
CREATE POLICY employer_subscriptions_select ON public.employer_subscriptions
    FOR SELECT TO authenticated, service_role
    USING (employer_id = (current_setting('request.jwt.claims', true)::json->>'user_id')::uuid);

-- _migrations (admin diagnostics, service_role only)
ALTER TABLE public._migrations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS migrations_select ON public._migrations;
CREATE POLICY migrations_select ON public._migrations
    FOR SELECT TO service_role USING (true);

-- schema_migrations (service_role only)
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS schema_migrations_select ON public.schema_migrations;
CREATE POLICY schema_migrations_select ON public.schema_migrations
    FOR SELECT TO service_role USING (true);

COMMIT;
