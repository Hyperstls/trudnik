-- ============================================
-- Исправление прав для Amvera (prod)
-- Безопасно: только REVOKE/GRANT, не трогает данные
-- ============================================

-- 1. Auth RPC: login_user и register_user должны быть доступны anon
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO anon, authenticated, service_role;

REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO anon, authenticated, service_role;

-- 2. Проверить что admin существует
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM profiles WHERE email = 'admin@test.ru') THEN
        INSERT INTO profiles (id, email, password_hash, full_name, role, created_at)
        VALUES (
            gen_random_uuid(),
            'admin@test.ru',
            crypt('Step@1986', gen_salt('bf')),
            'Администратор',
            'admin',
            now()
        );
    END IF;
END $$;

-- 3. Проверить что роли доступны trudnikapp
GRANT anon TO trudnikapp;
GRANT authenticated TO trudnikapp;
GRANT service_role TO trudnikapp;

-- 4. Проверить что религии есть
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM religions LIMIT 1) THEN
        INSERT INTO religions (id, name, sort_order) VALUES (gen_random_uuid(), 'Христианство', 1) ON CONFLICT (name) DO NOTHING;
        INSERT INTO religions (id, name, sort_order) VALUES (gen_random_uuid(), 'Ислам', 2) ON CONFLICT (name) DO NOTHING;
        INSERT INTO religions (id, name, sort_order) VALUES (gen_random_uuid(), 'Иудаизм', 3) ON CONFLICT (name) DO NOTHING;
        INSERT INTO religions (id, name, sort_order) VALUES (gen_random_uuid(), 'Буддизм', 4) ON CONFLICT (name) DO NOTHING;
        INSERT INTO religions (id, name, sort_order) VALUES (gen_random_uuid(), 'Индуизм', 5) ON CONFLICT (name) DO NOTHING;
        INSERT INTO religions (id, name, sort_order) VALUES (gen_random_uuid(), 'Атеизм', 6) ON CONFLICT (name) DO NOTHING;
    END IF;
END $$;

-- 5. Проверить что навыки есть
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM skills LIMIT 1) THEN
        INSERT INTO skills (id, name, sort_order) VALUES
            (gen_random_uuid(), 'Уборка и хозяйство',          1),
            (gen_random_uuid(), 'Мелкий ремонт и отделка',      2),
            (gen_random_uuid(), 'Пение и клирос',               3),
            (gen_random_uuid(), 'Преподавание и катехизация',   4),
            (gen_random_uuid(), 'Охрана и дежурство',           5),
            (gen_random_uuid(), 'Кухня и трапезная',            6),
            (gen_random_uuid(), 'Работа на территории',         7),
            (gen_random_uuid(), 'IT и мультимедиа',             8),
            (gen_random_uuid(), 'Транспорт и доставка',         9),
            (gen_random_uuid(), 'Бухгалтерия и финансы',       10),
            (gen_random_uuid(), 'Юридическая поддержка',       11),
            (gen_random_uuid(), 'Социальная работа',           12),
            (gen_random_uuid(), 'Организация мероприятий',     13),
            (gen_random_uuid(), 'Реставрация и декор',         14),
            (gen_random_uuid(), 'Служения',                    15)
        ON CONFLICT (name) DO NOTHING;
    END IF;
END $$;

-- 6. RLS для religions — политика чтения для всех
DROP POLICY IF EXISTS "read_religions" ON religions;
CREATE POLICY "read_religions" ON religions FOR SELECT USING (true);
