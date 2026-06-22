-- Скрипт: обновление пароля админа для Amvera (SHA-256)
-- Выполнить в SQL Editor базы данных Amvera

-- Пароль: Step@1986
-- SHA-256 хеш: 912be8f721a8f8667202d574769853ab082d469036446ee745f6feb257461609

UPDATE profiles
SET password_hash = '912be8f721a8f8667202d574769853ab082d469036446ee745f6feb257461609'
WHERE email = 'admin@test.ru';

-- Проверить результат
SELECT id, email, role, password_hash
FROM profiles
WHERE email = 'admin@test.ru';
