-- Migration 127: Fix PostGIS geo functions search_path (jobs_geom_update + nearby_jobs)
--
-- PROBLEM (production):
--   Creating/editing a job fails with
--     ERROR: function st_makepoint(double precision, double precision) does not exist
--     CONTEXT: PL/pgSQL function jobs_geom_update() line 4
--   although PostGIS IS available on Amvera (image cnpg/extensions:17.5, postgis enabled).
--
--   Root cause: migration 075 defined jobs_geom_update() and nearby_jobs() with
--   `SET search_path = ''` (empty). With an empty search_path, PostgreSQL cannot
--   resolve UNQUALIFIED PostGIS calls (ST_MakePoint, ST_SetSRID, ST_DWithin,
--   ST_Distance) which live in schema `public` — so every INSERT/UPDATE on jobs
--   fired trg_jobs_geom and aborted. (RLS and the search trigger were unrelated.)
--
--   Symptom was limited to jobs INSERT/UPDATE because all other mutations use
--   SECURITY DEFINER RPCs that bypass RLS; only direct `POST jobs` hit the trigger.
--
-- FIX:
--   1. Ensure PostGIS extension is active (CREATE EXTENSION IF NOT EXISTS).
--   2. Ensure jobs.geom column + GiST index exist.
--   3. Recreate jobs_geom_update() with search_path = pg_catalog, public AND
--      qualified public.ST_* calls (works regardless of caller's search_path).
--   4. Recreate trg_jobs_geom (was DROPped as an emergency workaround).
--   5. Recreate nearby_jobs() the same fixed way; restore GRANT.
--   6. Backfill geom for existing rows.
--
-- NOTE: CREATE EXTENSION requires SUPERUSER. Run as superuser (postgres) or via
--   pgAdmin connected as superuser. Idempotent throughout.
--
-- Deviation from rule 04 (`SET search_path = ''`): PostGIS-dependent functions
-- MUST include `public` in search_path (or qualify every call). Here we do both:
-- search_path = pg_catalog, public AND explicit public.ST_* qualification.

-- 1. PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. geom column + GiST index
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS geom public.geometry(public.Point, 4326);
CREATE INDEX IF NOT EXISTS idx_jobs_geom ON jobs USING GIST (geom);

-- 3. Trigger function (FIXED search_path + qualified PostGIS calls)
CREATE OR REPLACE FUNCTION public.jobs_geom_update() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $func$
BEGIN
    IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
        NEW.geom := public.ST_SetSRID(public.ST_MakePoint(NEW.lng, NEW.lat), 4326);
    END IF;
    RETURN NEW;
END;
$func$;

-- 4. Trigger
DROP TRIGGER IF EXISTS trg_jobs_geom ON jobs;
CREATE TRIGGER trg_jobs_geom
    BEFORE INSERT OR UPDATE OF lat, lng ON jobs
    FOR EACH ROW EXECUTE FUNCTION public.jobs_geom_update();

-- 5. nearby_jobs RPC (FIXED search_path + qualified PostGIS calls)
DROP FUNCTION IF EXISTS public.nearby_jobs(double precision, double precision, double precision);
DROP FUNCTION IF EXISTS public.nearby_jobs(double precision, double precision);

CREATE OR REPLACE FUNCTION public.nearby_jobs(
    p_lat double precision,
    p_lng double precision,
    p_radius_meters double precision DEFAULT 5000
)
RETURNS TABLE(
    id uuid, employer_id uuid, organization_name text, object_description text,
    work_type varchar, address varchar, city varchar, lat double precision,
    lng double precision, date_time timestamptz, payment_amount numeric,
    status varchar, max_workers int, current_workers int, created_at timestamptz,
    distance_meters double precision
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $func$
DECLARE
    v_point public.geometry := public.ST_SetSRID(public.ST_MakePoint(p_lng, p_lat), 4326);
BEGIN
    RETURN QUERY
    SELECT
        j.id, j.employer_id, j.organization_name, j.object_description,
        j.work_type, j.address, j.city, j.lat, j.lng,
        j.date_time, j.payment_amount, j.status, j.max_workers, j.current_workers,
        j.created_at,
        public.ST_Distance(j.geom::public.geography, v_point::public.geography) AS distance_meters
    FROM public.jobs j
    WHERE j.geom IS NOT NULL
      AND j.status = 'open'
      AND public.ST_DWithin(j.geom::public.geography, v_point::public.geography, p_radius_meters)
    ORDER BY j.geom <-> v_point
    LIMIT 50;
END;
$func$;

REVOKE EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) TO authenticated, service_role;

-- 6. Backfill geom for existing rows
UPDATE jobs
SET geom = public.ST_SetSRID(public.ST_MakePoint(lng, lat), 4326)
WHERE geom IS NULL AND lat IS NOT NULL AND lng IS NOT NULL;

ANALYZE jobs;
