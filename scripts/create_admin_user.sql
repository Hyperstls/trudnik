-- ============================================
-- Создание admin-пользователя вручную (pgAdmin)
-- ============================================
-- Замените email и пароль на свои!

DO $$
DECLARE
    v_admin_email text := 'admin@example.com';       -- ← ЗАМЕНИТЕ НА СВОЙ EMAIL
    v_admin_password text := 'CHANGE_ME';             -- ← ЗАМЕНИТЕ НА СВОЙ ПАРОЛЬ
BEGIN
    -- Защита: скрипт не должен выполняться с плейсхолдерами
    IF v_admin_email = 'admin@example.com' OR v_admin_password = 'CHANGE_ME' THEN
        RAISE EXCEPTION 'Замените email и пароль перед выполнением скрипта!';
    END IF;

    -- Если пользователь с таким email уже существует — обновляем роль
    IF EXISTS (SELECT 1 FROM profiles WHERE email = v_admin_email) THEN
        UPDATE profiles 
        SET role = 'admin',
            password_hash = crypt(v_admin_password, gen_salt('bf'))
        WHERE email = v_admin_email;
        RAISE NOTICE 'Пользователь % обновлён: роль=admin, пароль обновлён', v_admin_email;
    ELSE
        INSERT INTO profiles (id, email, password_hash, full_name, role)
        VALUES (
            gen_random_uuid(),
            v_admin_email,
            crypt(v_admin_password, gen_salt('bf')),
            'Администратор',
            'admin'
        );
        RAISE NOTICE 'Admin-пользователь создан: %', v_admin_email;
    END IF;
END $$;

-- Проверка
SELECT id, email, full_name, role, created_at 
FROM profiles 
WHERE role = 'admin';
