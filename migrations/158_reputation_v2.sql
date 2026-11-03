-- J162: reputation v2 — role-specific aggregates, double-blind publication,
-- structured criteria/tags, replies, reports and review moderation.
--
-- Existing ratings are backfilled as published (legacy reviews were public
-- immediately). New ratings start with published_at = NULL and become public
-- after the counterpart rates or after the 14-day deadline.

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS worker_rating double precision NOT NULL DEFAULT 0;
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS worker_ratings_count integer NOT NULL DEFAULT 0;
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS employer_rating double precision NOT NULL DEFAULT 0;
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS employer_ratings_count integer NOT NULL DEFAULT 0;

ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS published_at timestamptz;
ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS criteria jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS reply text;
ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS replied_at timestamptz;
ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS moderation_status text NOT NULL DEFAULT 'ok';
ALTER TABLE ratings
    ADD COLUMN IF NOT EXISTS moderation_reason text;

DO $$ BEGIN
    ALTER TABLE ratings ADD CONSTRAINT ratings_moderation_status_check
        CHECK (moderation_status IN ('ok', 'review', 'hidden'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS ratings_public_idx
    ON ratings (rated_user_id, target_type, published_at DESC)
    WHERE published_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS ratings_job_pair_idx
    ON ratings (job_id, rater_user_id, rated_user_id);

CREATE TABLE IF NOT EXISTS rating_reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rating_id uuid NOT NULL REFERENCES ratings(id) ON DELETE CASCADE,
    reporter_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'new',
    reviewed_by uuid REFERENCES profiles(id) ON DELETE SET NULL,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (rating_id, reporter_id)
);
CREATE INDEX IF NOT EXISTS rating_reports_status_idx
    ON rating_reports (status, created_at DESC);
GRANT SELECT, INSERT, UPDATE, DELETE ON rating_reports TO trudnik_dj;

-- Legacy ratings were public immediately: publish them and leave the new
-- rating pipeline for future rows.
UPDATE ratings
SET published_at = COALESCE(published_at, created_at, now())
WHERE published_at IS NULL;

-- Role-specific averages and counts; only public, non-hidden reviews count.
-- total_reviews is kept in sync with ratings_count (the UI used total_reviews).
CREATE OR REPLACE FUNCTION recompute_profile_rating()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_rated_user_id uuid;
    v_worker_rating numeric;
    v_worker_count integer;
    v_employer_rating numeric;
    v_employer_count integer;
    v_all_rating numeric;
    v_all_count integer;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_rated_user_id := OLD.rated_user_id;
    ELSE
        v_rated_user_id := NEW.rated_user_id;
    END IF;

    SELECT
        COALESCE(ROUND(AVG(rating) FILTER (WHERE target_type = 'worker')::numeric, 1), 0),
        COUNT(*) FILTER (WHERE target_type = 'worker'),
        COALESCE(ROUND(AVG(rating) FILTER (WHERE target_type = 'employer')::numeric, 1), 0),
        COUNT(*) FILTER (WHERE target_type = 'employer'),
        COALESCE(ROUND(AVG(rating)::numeric, 1), 0),
        COUNT(*)
    INTO v_worker_rating, v_worker_count, v_employer_rating, v_employer_count,
         v_all_rating, v_all_count
    FROM public.ratings
    WHERE rated_user_id = v_rated_user_id
      AND published_at IS NOT NULL
      AND moderation_status = 'ok';

    UPDATE public.profiles
    SET worker_rating = v_worker_rating,
        worker_ratings_count = v_worker_count,
        employer_rating = v_employer_rating,
        employer_ratings_count = v_employer_count,
        rating = v_all_rating,
        ratings_count = v_all_count,
        total_reviews = v_all_count
    WHERE id = v_rated_user_id;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS trg_recompute_rating ON public.ratings;
CREATE TRIGGER trg_recompute_rating
    AFTER INSERT OR UPDATE OR DELETE ON public.ratings
    FOR EACH ROW EXECUTE FUNCTION recompute_profile_rating();

REVOKE EXECUTE ON FUNCTION recompute_profile_rating() FROM PUBLIC;

-- Backfill aggregates for existing data.
UPDATE profiles p
SET worker_rating = COALESCE(x.worker_rating, 0),
    worker_ratings_count = COALESCE(x.worker_count, 0),
    employer_rating = COALESCE(x.employer_rating, 0),
    employer_ratings_count = COALESCE(x.employer_count, 0),
    rating = COALESCE(x.all_rating, 0),
    ratings_count = COALESCE(x.all_count, 0),
    total_reviews = COALESCE(x.all_count, 0)
FROM (
    SELECT rated_user_id,
           ROUND(AVG(rating) FILTER (WHERE target_type = 'worker')::numeric, 1) AS worker_rating,
           COUNT(*) FILTER (WHERE target_type = 'worker') AS worker_count,
           ROUND(AVG(rating) FILTER (WHERE target_type = 'employer')::numeric, 1) AS employer_rating,
           COUNT(*) FILTER (WHERE target_type = 'employer') AS employer_count,
           ROUND(AVG(rating)::numeric, 1) AS all_rating,
           COUNT(*) AS all_count
    FROM ratings
    WHERE published_at IS NOT NULL AND moderation_status = 'ok'
    GROUP BY rated_user_id
) x
WHERE p.id = x.rated_user_id;

-- rate_user_atomic: both sides (worker→employer and employer→worker) are valid.
-- Aggregates are recalculated by trg_recompute_rating, not manually here.
CREATE OR REPLACE FUNCTION public.rate_user_atomic(
    p_job_id uuid,
    p_rater_user_id uuid,
    p_rated_user_id uuid,
    p_rating int,
    p_comment text DEFAULT '',
    p_rating_type text DEFAULT 'worker',
    p_target_type text DEFAULT 'worker'
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF p_rating < 1 OR p_rating > 5 THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Рейтинг должен быть от 1 до 5', 'code', 'invalid_rating'
        );
    END IF;

    IF p_rater_user_id = p_rated_user_id THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Нельзя оценить самого себя', 'code', 'self_rating'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.jobs WHERE id = p_job_id AND status = 'completed'
    ) THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Оценить можно только завершённое задание', 'code', 'job_not_completed'
        );
    END IF;

    -- Both the employer and an accepted worker are valid participants.
    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = p_job_id AND employer_id = p_rater_user_id
    ) AND NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id AND worker_id = p_rater_user_id AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Вы не участвовали в этом задании', 'code', 'not_participant'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = p_job_id AND employer_id = p_rated_user_id
    ) AND NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id AND worker_id = p_rated_user_id AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Оцениваемый пользователь не участвовал в этом задании',
            'code', 'rated_not_participant'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE id = p_rated_user_id
    ) THEN
        RETURN jsonb_build_object(
            'success', false, 'error', 'Оцениваемый пользователь не найден', 'code', 'user_not_found'
        );
    END IF;

    INSERT INTO public.ratings (
        job_id, rater_user_id, rated_user_id, rating, comment,
        rating_type, target_type, created_at, updated_at
    ) VALUES (
        p_job_id, p_rater_user_id, p_rated_user_id, p_rating, p_comment,
        p_rating_type, p_target_type, now(), now()
    )
    ON CONFLICT (rater_user_id, job_id, rated_user_id)
    DO UPDATE SET
        rating = EXCLUDED.rating,
        comment = EXCLUDED.comment,
        updated_at = now();

    RETURN jsonb_build_object('success', true, 'message', 'Оценка сохранена');
END;
$$;

REVOKE EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';
