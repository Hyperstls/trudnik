-- Повысить существующего пользователя до admin
-- Замените email на нужный!
UPDATE profiles 
SET role = 'admin' 
WHERE email = 'ваш@email.ru'  -- ← ЗАМЕНИТЕ
RETURNING id, email, full_name, role;
