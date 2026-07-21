"""X5: admin.py must use session.get('user_id') not session.get('user', {}).get('id')."""
import inspect


def test_admin_log_uses_session_user_id():
    """X5: log_admin_action must use session.get('user_id')."""
    from app.blueprints import admin
    
    source = inspect.getsource(admin.log_admin_action)
    
    # Проверить, что НЕ используется старый паттерн
    assert "session.get('user', {}).get('id')" not in source, \
        "log_admin_action must not use session.get('user', {}).get('id')"
    
    # Проверить, что используется правильный паттерн
    assert "session.get('user_id')" in source, \
        "log_admin_action must use session.get('user_id')"
