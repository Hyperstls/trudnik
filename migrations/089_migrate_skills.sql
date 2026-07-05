-- ============================================================================
-- Миграция 089: Перенести profiles.skills → user_skills и удалить колонку
-- Проблема: Навыки дублируются — массив text[] в profiles.skills и таблица user_skills.
-- Решение: Перенос данных в user_skills, затем DROP COLUMN profiles.skills.
-- Идемпотентность: проверка information_schema.columns перед миграцией.
-- ============================================================================

DO $$
DECLARE
    v_rec RECORD;
    v_skill_name text;
    v_skill_id uuid;
BEGIN
    -- Проверяем, существует ли ещё колонка skills (идемпотентность)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'profiles' AND column_name = 'skills') THEN

        -- Шаг 1: Перенести существующие навыки из profiles.skills (text[]) в user_skills
        FOR v_rec IN
            SELECT id, unnest(skills) AS skill_name
            FROM public.profiles
            WHERE skills IS NOT NULL AND array_length(skills, 1) > 0
        LOOP
            -- Нормализуем имя навыка
            v_skill_name := trim(both ' "' FROM v_rec.skill_name);
            IF v_skill_name = '' THEN
                CONTINUE;
            END IF;

            -- Ищем skill_id по имени (игнорируя регистр)
            SELECT id INTO v_skill_id
            FROM public.skills
            WHERE LOWER(name) = LOWER(v_skill_name)
            LIMIT 1;

            -- Если навык не найден в справочнике — создаём
            IF v_skill_id IS NULL THEN
                INSERT INTO public.skills (name) VALUES (v_skill_name)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id INTO v_skill_id;
                IF v_skill_id IS NULL THEN
                    SELECT id INTO v_skill_id FROM public.skills
                    WHERE LOWER(name) = LOWER(v_skill_name)
                    LIMIT 1;
                END IF;
            END IF;

            -- Вставляем связь user-skill (пропускаем дубликаты)
            IF v_skill_id IS NOT NULL THEN
                INSERT INTO public.user_skills (user_id, skill_id)
                VALUES (v_rec.id, v_skill_id)
                ON CONFLICT DO NOTHING;
            END IF;
        END LOOP;

        -- Шаг 2: Удалить колонку skills из profiles
        ALTER TABLE public.profiles DROP COLUMN IF EXISTS skills;

    END IF;
END $$;
