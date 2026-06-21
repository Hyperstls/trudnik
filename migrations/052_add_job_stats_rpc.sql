-- ============================================================================
-- Миграция 052: RPC get_job_stats для серверной агрегации статистики заданий
-- Дата: 2026-06-21
-- Контекст: эндпоинт /api/admin/job-stats загружал ВСЕ задания в Python
--   для подсчёта статусов (O(n)). Данная RPC выполняет агрегацию на сервере (O(1)).
-- Идемпотентна: CREATE OR REPLACE.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_job_stats()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    _result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total', COUNT(*),
        'open', COUNT(*) FILTER (WHERE status = 'open'),
        'completed', COUNT(*) FILTER (WHERE status = 'completed'),
        'cancelled', COUNT(*) FILTER (WHERE status = 'cancelled')
    ) INTO _result
    FROM public.jobs;
    RETURN _result;
END;
$$;

-- Права: только service_role (админские запросы)
GRANT EXECUTE ON FUNCTION public.get_job_stats() TO service_role;
REVOKE EXECUTE ON FUNCTION public.get_job_stats() FROM anon, authenticated, PUBLIC;
