-- Migration 128: Fix delete_job_cascade — favorites → job_favorites
--
-- PROBLEM (production):
--   Deleting a job (single or bulk) fails:
--     ERROR: column "job_id" does not exist
--     LINE 1: DELETE FROM public.favorites WHERE job_id=p_job_id
--     CONTEXT: PL/pgSQL function delete_job_cascade(uuid) line 10
--
--   Root cause: migration 099 recreated delete_job_cascade() with
--   `DELETE FROM public.favorites WHERE job_id = p_job_id`, but the `favorites`
--   table holds favourite WORKERS/EMPLOYERS (columns: user_id, target_id,
--   favorite_type) and has NO job_id column. Favourite JOBS live in the separate
--   `job_favorites` table (columns: user_id, job_id) — which migration 091 used
--   correctly. 099 regressed to the wrong table.
--
--   Effect: the SECURITY DEFINER RPC aborted at line 10 → PostgREST returned
--   non-2xx → single delete surfaced as "Ошибка соединения" (handler redirected
--   instead of JSON) and bulk delete as "Ошибка удаления задания".
--
-- FIX: recreate delete_job_cascade() deleting from `job_favorites` (correct table).
-- Everything else matches the 099 version (RETURN jsonb, SECURITY DEFINER,
-- search_path=''; all references are public.-qualified or pg_catalog built-ins,
-- so empty search_path is safe here). Idempotent.

DROP FUNCTION IF EXISTS public.delete_job_cascade(uuid) CASCADE;

CREATE OR REPLACE FUNCTION public.delete_job_cascade(p_job_id uuid)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE
    v_eid uuid; va int; vs int; vp int; vf int; vi int; vn int;
BEGIN
    SELECT employer_id INTO v_eid FROM public.jobs WHERE id = p_job_id;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error', 'not_found');
    END IF;

    DELETE FROM public.applications   WHERE job_id = p_job_id; GET DIAGNOSTICS va = ROW_COUNT;
    DELETE FROM public.job_skills     WHERE job_id = p_job_id; GET DIAGNOSTICS vs = ROW_COUNT;
    DELETE FROM public.job_photos     WHERE job_id = p_job_id; GET DIAGNOSTICS vp = ROW_COUNT;
    DELETE FROM public.job_favorites  WHERE job_id = p_job_id; GET DIAGNOSTICS vf = ROW_COUNT;  -- FIX: job_favorites (was: favorites)
    DELETE FROM public.invitations    WHERE job_id = p_job_id; GET DIAGNOSTICS vi = ROW_COUNT;
    DELETE FROM public.notifications  WHERE job_id = p_job_id; GET DIAGNOSTICS vn = ROW_COUNT;
    DELETE FROM public.jobs           WHERE id      = p_job_id;

    RETURN jsonb_build_object(
        'success', true,
        'deleted_applications', va,
        'deleted_skills', vs,
        'deleted_photos', vp,
        'deleted_favorites', vf,
        'deleted_invitations', vi,
        'deleted_notifications', vn
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.delete_job_cascade(uuid) FROM PUBLIC;
GRANT  EXECUTE ON FUNCTION public.delete_job_cascade(uuid) TO authenticated, service_role;
