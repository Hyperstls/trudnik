"""X7: login_required must check jti blacklist."""
import inspect


def test_is_jti_blacklisted_exists():
    """X7: is_jti_blacklisted function must exist in app.utils.auth."""
    from app.utils import auth
    
    assert hasattr(auth, 'is_jti_blacklisted'), \
        "is_jti_blacklisted must exist in app.utils.auth"
    assert callable(auth.is_jti_blacklisted), \
        "is_jti_blacklisted must be callable"


def test_login_required_checks_jti_blacklist():
    """X7: login_required must check jti blacklist."""
    from app import decorators
    
    source = inspect.getsource(decorators.login_required)
    
    # Проверить, что есть проверка jti
    assert 'jti' in source, \
        "login_required must extract jti from token"
    
    # Проверить, что вызывается is_jti_blacklisted
    assert 'is_jti_blacklisted' in source, \
        "login_required must call is_jti_blacklisted"
