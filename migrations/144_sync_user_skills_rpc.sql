-- 144: sync_user_skills — атомарная синхронизация навыков пользователя.
-- Заменяет неатомарный паттерн «DELETE всех user_skills + N отдельных INSERT»
-- в регистрации (auth.py) и обновлении профиля (profile.py): при падении
-- посередине профиль оставался с частичными навыками. Теперь DELETE+INSERT
-- выполняются в одной транзакции функции.
--
-- Семантика:
--   - DELETE связей, не входящих в p_skill_ids (пустой массив '{}' → удалить все);
--   - INSERT новых связей (ON CONFLICT DO NOTHING — PK (user_id, skill_id));
--   - несуществующие skill_id тихо пропускаются (как старый код с FK-ошибками).
--
-- Доступ: вызывающий = p_user_id (user_id из JWT claims) ИЛИ service_role
-- (регистрация идёт через service_role — пользователь ещё не залогинен).

CREATE OR REPLACE FUNCTION public.sync_user_skills(
    p_user_id uuid,
    p_skill_ids uuid[]
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_claims json;
    v_caller uuid;
    v_role   text;
BEGIN
    -- Проверка вызывающего: сам пользователь ИЛИ service_role.
    -- PostgREST v14 отдаёт claims одним JSON-GUC (миграция 124/125).
    v_claims := current_setting('request.jwt.claims', true)::json;
    v_caller := (v_claims->>'user_id')::uuid;
    v_role   := v_claims->>'role';
    IF v_role IS DISTINCT FROM 'service_role'
       AND (v_caller IS NULL OR v_caller <> p_user_id) THEN
        RAISE EXCEPTION 'forbidden: cannot sync skills of another user'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- Удаляем связи, которых нет в новом массиве.
    -- '<> ALL' от пустого массива истинно для каждой строки → DELETE всех.
    DELETE FROM public.user_skills
    WHERE user_id = p_user_id
      AND skill_id <> ALL (COALESCE(p_skill_ids, '{}'::uuid[]));

    -- Вставляем новые связи; дубликаты (уже существующие) пропускаем,
    -- навыки, отсутствующие в справочнике skills, — тоже (старое поведение).
    INSERT INTO public.user_skills (user_id, skill_id)
    SELECT p_user_id, s
    FROM unnest(COALESCE(p_skill_ids, '{}'::uuid[])) AS s
    WHERE s IN (SELECT id FROM public.skills)
    ON CONFLICT DO NOTHING;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.sync_user_skills(uuid, uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.sync_user_skills(uuid, uuid[]) TO authenticated, service_role;

NOTIFY pgrst, 'reload schema';
