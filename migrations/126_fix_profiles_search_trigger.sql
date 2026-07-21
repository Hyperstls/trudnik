-- Migration 126: Fix profiles_search_update() trigger — drop removed NEW.skills column reference
--
-- PROBLEM:
--   Saving a profile (POST /profile/update → PATCH profiles) fails with
--   400 {"code":"42703","message":"record \"new\" has no field \"skills\""}.
--   The BEFORE INSERT/UPDATE trigger trg_profiles_search calls
--   profiles_search_update(), which references NEW.skills — but the `skills`
--   column was moved to the `user_skills` table (migration 089) and dropped
--   from `profiles`. So every profile write errors.
--
-- FIX:
--   Recreate profiles_search_update() to aggregate skill names from
--   user_skills⨝skills instead of the dropped column. SECURITY DEFINER +
--   schema-qualified tables so it works for any invoking role.
--
-- Idempotent (CREATE OR REPLACE). Verified locally.

CREATE OR REPLACE FUNCTION public.profiles_search_update() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.full_name, '')), 'A') ||
        setweight(to_tsvector('russian', coalesce(
            (SELECT string_agg(s.name, ' ')
               FROM public.user_skills us
               JOIN public.skills s ON s.id = us.skill_id
              WHERE us.user_id = NEW.id), '')), 'B') ||
        setweight(to_tsvector('russian', coalesce(NEW.bio, '')), 'C') ||
        setweight(to_tsvector('russian', coalesce(NEW.city, '')), 'D');
    RETURN NEW;
END;
$$;

-- Пересчитать search_vector для уже существующих профилей (функция выше
-- корректна; UPDATE запускает триггер). Обновляет updated_at — это metadata.
UPDATE public.profiles SET updated_at = updated_at;
