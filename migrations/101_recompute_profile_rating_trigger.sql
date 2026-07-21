-- ============================================================================
-- Миграция 101: PostgreSQL trigger для атомарного пересчёта рейтинга
-- Проблема: read-modify-write race condition при обновлении рейтинга профиля
-- Решение: триггер автоматически пересчитывает AVG и COUNT при изменении ratings
-- ============================================================================
BEGIN;

CREATE OR REPLACE FUNCTION recompute_profile_rating()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_rated_user_id uuid;
    v_avg_rating numeric;
    v_count integer;
BEGIN
    -- Определяем rated_user_id из NEW или OLD записи
    IF TG_OP = 'DELETE' THEN
        v_rated_user_id := OLD.rated_user_id;
    ELSE
        v_rated_user_id := NEW.rated_user_id;
    END IF;
    
    -- Пересчитываем средний рейтинг атомарно
    SELECT COALESCE(ROUND(AVG(rating)::numeric, 1), 0), COUNT(*)::int
    INTO v_avg_rating, v_count
    FROM public.ratings
    WHERE rated_user_id = v_rated_user_id;
    
    -- Обновляем профиль
    UPDATE public.profiles
    SET rating = v_avg_rating,
        ratings_count = v_count
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

COMMIT;
