-- ============================================================================
-- Миграция 056: RPC nearby_jobs — геопоиск заданий по радиусу
-- Дата: 2026-06-21
-- Контекст: В облачном Supabase существует RPC nearby_jobs, отсутствующая локально.
--   Функция использует PostGIS для поиска заданий в заданном радиусе.
-- Идемпотентна: CREATE OR REPLACE.
-- ============================================================================

-- PostGIS должен быть установлен для работы ST_DWithin
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE OR REPLACE FUNCTION public.nearby_jobs(
    lat double precision,
    lng double precision,
    radius_km double precision DEFAULT 50
)
RETURNS SETOF jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = 'public'
AS $$
DECLARE
    _point geometry;
    _radius_meters double precision;
BEGIN
    _point := ST_SetSRID(ST_MakePoint(lng, lat), 4326);
    _radius_meters := radius_km * 1000;

    RETURN QUERY
    SELECT j.*
    FROM jobs j
    WHERE j.status = 'open'
      AND j.lat IS NOT NULL
      AND j.lng IS NOT NULL
      AND ST_DWithin(
            ST_SetSRID(ST_MakePoint(j.lng, j.lat), 4326)::geography,
            _point::geography,
            _radius_meters
          )
    ORDER BY
        ST_Distance(
            ST_SetSRID(ST_MakePoint(j.lng, j.lat), 4326)::geography,
            _point::geography
        );
END;
$$;

-- Права: только authenticated (пользователи приложения)
GRANT EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) TO authenticated;
REVOKE EXECUTE ON FUNCTION public.nearby_jobs(double precision, double precision, double precision) FROM anon, PUBLIC;

-- ============================================================================
-- ГОТОВО!
-- ============================================================================
