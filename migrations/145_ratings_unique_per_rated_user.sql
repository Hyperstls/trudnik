-- 145: ratings — уникальность оценки по тройке (rater_user_id, job_id, rated_user_id).
--
-- Проблема: UNIQUE (rater_user_id, job_id) из 067 (ratings_rater_job_unique)
-- не давал работодателю оценить нескольких исполнителей одного задания —
-- UPSERT в POST /api/ratings (app/blueprints/ratings.py) искал существующую
-- оценку по паре (rater, job), и вторая оценка другому работнику
-- перезаписывала первую.
--
-- Правильная семантика: одна оценка на пару (оценщик, оцениваемый) в рамках
-- задания → ключ (rater_user_id, job_id, rated_user_id).
--
-- Что делает миграция:
--   1. Страховочно удаляет дубли по новой тройке (при действующем старом
--      UNIQUE их быть не может, но если constraint где-то потерян — чистим,
--      оставляя самую свежую по updated_at запись);
--   2. Удаляет старый UNIQUE ratings_rater_job_unique (причина бага);
--   3. Добавляет новый UNIQUE ratings_rater_job_rated_unique;
--   4. Пересоздаёт RPC rate_user_atomic с ON CONFLICT по трём колонкам
--      (она ссылается на старый constraint — после его удаления RPC падала
--      бы с 42P10 «no unique constraint matching ON CONFLICT»).
--
-- Идемпотентно: все шаги с проверками, повторный прогон — no-op.

DO $$
DECLARE
    v_deleted int;
BEGIN
    -- 1. Зачистка дублей по (rater_user_id, job_id, rated_user_id):
    --    оставляем самую свежую запись (updated_at, затем created_at).
    WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY rater_user_id, job_id, rated_user_id
                   ORDER BY updated_at DESC NULLS LAST,
                            created_at DESC NULLS LAST,
                            id
               ) AS rn
        FROM public.ratings
    )
    DELETE FROM public.ratings r
    USING ranked
    WHERE r.id = ranked.id
      AND ranked.rn > 1;

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    IF v_deleted > 0 THEN
        RAISE NOTICE 'ratings: удалено % дублей по (rater_user_id, job_id, rated_user_id)', v_deleted;
    END IF;

    -- 2. Старый UNIQUE (rater_user_id, job_id) — причина бага.
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ratings_rater_job_unique'
          AND conrelid = 'public.ratings'::regclass
    ) THEN
        ALTER TABLE public.ratings DROP CONSTRAINT ratings_rater_job_unique;
        RAISE NOTICE 'ratings: удалён constraint ratings_rater_job_unique';
    END IF;

    -- 3. Новый UNIQUE по тройке (оценщик, задание, оцениваемый).
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ratings_rater_job_rated_unique'
          AND conrelid = 'public.ratings'::regclass
    ) THEN
        ALTER TABLE public.ratings
            ADD CONSTRAINT ratings_rater_job_rated_unique
            UNIQUE (rater_user_id, job_id, rated_user_id);
        RAISE NOTICE 'ratings: добавлен constraint ratings_rater_job_rated_unique';
    END IF;
END $$;

-- 4. rate_user_atomic: ON CONFLICT по новой тройке.
--    Логика — без изменений относительно версии из 069 (проверки участия
--    обоих пользователей в задании), меняется только цель ON CONFLICT:
--    (rater_user_id, job_id) → (rater_user_id, job_id, rated_user_id).
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
DECLARE
    v_new_avg numeric(3,1);
    v_new_count int;
BEGIN
    -- 1. Валидация рейтинга
    IF p_rating < 1 OR p_rating > 5 THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Рейтинг должен быть от 1 до 5',
            'code', 'invalid_rating'
        );
    END IF;

    -- 2. Нельзя оценить самого себя
    IF p_rater_user_id = p_rated_user_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Нельзя оценить самого себя',
            'code', 'self_rating'
        );
    END IF;

    -- 3. Проверить, что задание существует и завершено
    IF NOT EXISTS (
        SELECT 1 FROM public.jobs
        WHERE id = p_job_id AND status = 'completed'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оценить можно только завершённое задание',
            'code', 'job_not_completed'
        );
    END IF;

    -- 4. Проверка участия оценивающего в задании
    IF NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id
        AND worker_id = p_rater_user_id
        AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Вы не участвовали в этом задании',
            'code', 'not_participant'
        );
    END IF;

    -- 5. Проверка участия оцениваемого в задании
    IF NOT EXISTS (
        SELECT 1 FROM public.applications
        WHERE job_id = p_job_id
        AND worker_id = p_rated_user_id
        AND status = 'accepted'
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не участвовал в этом задании',
            'code', 'rated_not_participant'
        );
    END IF;

    -- 6. Проверить, что оцениваемый пользователь существует
    IF NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE id = p_rated_user_id
    ) THEN
        RETURN jsonb_build_object(
            'success', false,
            'error', 'Оцениваемый пользователь не найден',
            'code', 'user_not_found'
        );
    END IF;

    -- 7. UPSERT оценки (одна оценка на пару оценщик–оцениваемый в рамках задания)
    INSERT INTO public.ratings (
        job_id,
        rater_user_id,
        rated_user_id,
        rating,
        comment,
        rating_type,
        target_type,
        created_at,
        updated_at
    ) VALUES (
        p_job_id,
        p_rater_user_id,
        p_rated_user_id,
        p_rating,
        p_comment,
        p_rating_type,
        p_target_type,
        now(),
        now()
    )
    ON CONFLICT (rater_user_id, job_id, rated_user_id)
    DO UPDATE SET
        rating = EXCLUDED.rating,
        comment = EXCLUDED.comment,
        updated_at = now();

    -- 8. Пересчитать средний рейтинг и количество оценок для rated_user_id
    SELECT
        COALESCE(ROUND(AVG(rating)::numeric, 1), 0),
        COUNT(*)::int
    INTO v_new_avg, v_new_count
    FROM public.ratings
    WHERE rated_user_id = p_rated_user_id;

    -- 9. Обновить профиль пользователя
    UPDATE public.profiles
    SET rating = v_new_avg,
        ratings_count = v_new_count
    WHERE id = p_rated_user_id;

    RETURN jsonb_build_object(
        'success', true,
        'message', 'Оценка сохранена',
        'new_avg_rating', v_new_avg,
        'new_ratings_count', v_new_count
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.rate_user_atomic(uuid, uuid, uuid, int, text, text, text) TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';
