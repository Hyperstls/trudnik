-- Отозвать EXECUTE от anon для публичных RPC
REVOKE EXECUTE ON FUNCTION login_user(text, text) FROM anon;
GRANT EXECUTE ON FUNCTION login_user(text, text) TO authenticated, service_role;

REVOKE EXECUTE ON FUNCTION register_user(text, text, text, text) FROM anon;
GRANT EXECUTE ON FUNCTION register_user(text, text, text, text) TO authenticated, service_role;