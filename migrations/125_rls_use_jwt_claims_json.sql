-- Migration 125: Rewrite RLS policies to read JWT claims from request.jwt.claims (JSON)
--
-- Companion/alternative to 124. PostgREST v12/v14 exposes the JWT only as
-- `request.jwt.claims` (JSON); the individual `request.jwt.claim.<name>` GUCs
-- are NOT set, so policies written as
--     current_setting('request.jwt.claim.user_id', true)::uuid = id
-- evaluated to NULL and filtered out every row.
--
-- This migration rewrites every affected policy's USING / WITH CHECK expression,
-- replacing
--     current_setting('request.jwt.claim.<name>'::text, true)
-- with
--     (current_setting('request.jwt.claims'::text, true)::json->>'<name>')
-- so policies work WITHOUT any PostgREST pre-request configuration.
--
-- Idempotent: the regexp only matches the old `request.jwt.claim.<name>` form,
-- so re-running is a no-op. Tested locally.

DO $$
DECLARE
    r record;
    using_expr text;
    check_expr text;
    cmd text;
    perm text;
    stmt text;
BEGIN
    FOR r IN
        SELECT c.relname AS tbl,
               p.polname AS pname,
               p.polcmd  AS pcmd,
               p.polpermissive AS pperm,
               pg_get_expr(p.polqual, p.polrelid)      AS q,
               pg_get_expr(p.polwithcheck, p.polrelid) AS wc
        FROM pg_policy p
        JOIN pg_class c        ON c.oid = p.polrelid
        JOIN pg_namespace n    ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND (
                pg_get_expr(p.polqual, p.polrelid)      ~ 'request\.jwt\.claim\.'
             OR pg_get_expr(p.polwithcheck, p.polrelid) ~ 'request\.jwt\.claim\.'
          )
    LOOP
        using_expr := regexp_replace(
            COALESCE(r.q, ''),
            'current_setting\(''request\.jwt\.claim\.([a-z_]+)''::text, true\)',
            '(current_setting(''request.jwt.claims''::text, true)::json->>''\1'')',
            'g');
        check_expr := regexp_replace(
            COALESCE(r.wc, ''),
            'current_setting\(''request\.jwt\.claim\.([a-z_]+)''::text, true\)',
            '(current_setting(''request.jwt.claims''::text, true)::json->>''\1'')',
            'g');

        cmd  := CASE r.pcmd WHEN '*' THEN 'ALL' WHEN 'r' THEN 'SELECT'
                            WHEN 'a' THEN 'INSERT' WHEN 'w' THEN 'UPDATE'
                            WHEN 'd' THEN 'DELETE' END;
        perm := CASE WHEN r.pperm THEN '' ELSE ' AS RESTRICTIVE' END;

        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', r.pname, r.tbl);

        stmt := format('CREATE POLICY %I ON public.%I FOR %s%s', r.pname, r.tbl, cmd, perm);
        IF r.pcmd IN ('*', 'r', 'w', 'd') AND using_expr <> '' THEN
            stmt := stmt || format(' USING (%s)', using_expr);
        END IF;
        IF r.pcmd IN ('*', 'a', 'w') AND check_expr <> '' THEN
            stmt := stmt || format(' WITH CHECK (%s)', check_expr);
        END IF;
        EXECUTE stmt;
    END LOOP;
END $$;
