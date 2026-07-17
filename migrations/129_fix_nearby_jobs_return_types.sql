-- Migration 129: Fix nearby_jobs RETURN-type mismatch (varchar vs text)
--
-- PROBLEM (production):
--   SELECT * FROM nearby_jobs(55.75, 37.61, 50000) fails:
--     ERROR: structure of query does not match function result type
--     Returned type text does not match expected type character varying
--     in column 12. (column 12 = status)
--   Root cause: the RETURN TABLE declared status (and other string columns) as
--   `varchar`, but the actual jobs columns are `text` in prod. The bootstrap
--   uses `CREATE TABLE IF NOT EXISTS jobs`, so a pre-existing jobs table (with
--   status text) was not overwritten — types drifted from the migration source.
--
-- FIX: keep the RETURN TABLE declarations, but explicitly cast every column in
--   the SELECT to its declared type. Explicit casts (e.g. j.status::varchar)
--   work whether the underlying column is text or varchar, so the function is
--   immune to further type drift. No behaviour change otherwise.
--   Idempotent (CREATE OR REPLACE). Requires PostGIS (search_path includes public).

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
        j.id::uuid, j.employer_id::uuid,
        j.organization_name::text, j.object_description::text,
        j.work_type::varchar, j.address::varchar, j.city::varchar,
        j.lat::double precision, j.lng::double precision,
        j.date_time::timestamptz, j.payment_amount::numeric,
        j.status::varchar, j.max_workers::int, j.current_workers::int,
        j.created_at::timestamptz,
        public.ST_Distance(j.geom::public.geography, v_point::public.geography)::double precision AS distance_meters
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
