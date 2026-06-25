-- =============================================================
-- Fix auth RPC permissions (login_user, register_user, change_password)
-- 
-- Проблема: PostgREST RPC возвращает 403 "permission denied for function"
-- при вызове login_user и register_user, несмотря на GRANT,
-- т.к. в миграции 067 GRANTы выполнены без схемы public.
-- Решение: явный GRANT с указанием схемы public для каждой функции.
-- =============================================================

BEGIN;

-- 1. login_user — вызывается при входе (auth/login)
GRANT EXECUTE ON FUNCTION public.login_user(
    email    TEXT,
    password TEXT
) TO anon, authenticated, service_role;

-- 2. register_user — вызывается при регистрации
GRANT EXECUTE ON FUNCTION public.register_user(
    email     TEXT,
    password  TEXT,
    role      TEXT,
    full_name TEXT
) TO anon, authenticated, service_role;

-- 3. change_password — вызывается при смене пароля
GRANT EXECUTE ON FUNCTION public.change_password(
    user_id       UUID,
    old_password  TEXT,
    new_password  TEXT
) TO authenticated, service_role;

COMMIT;
