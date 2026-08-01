-- 136_expire_unfilled_jobs.sql
-- Phase 3 / bugfix: просроченные задания БЕЗ откликов автоматически завершаются
-- по достижении времени начала (date_time) и не показываются трудникам
-- (jobs.index показывает status in (open,completed) — 'expired' исключён).
-- Идемпотентно. SECURITY DEFINER (service_role).

CREATE OR REPLACE FUNCTION expire_unfilled_jobs()
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $$
DECLARE v_count integer;
BEGIN
    UPDATE jobs
       SET status = 'expired', updated_at = now()
     WHERE status = 'open'
       AND date_time IS NOT NULL
       AND date_time < now()
       AND NOT EXISTS (
           SELECT 1 FROM applications WHERE applications.job_id = jobs.id
       );
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
REVOKE EXECUTE ON FUNCTION expire_unfilled_jobs() FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION expire_unfilled_jobs() TO service_role;
