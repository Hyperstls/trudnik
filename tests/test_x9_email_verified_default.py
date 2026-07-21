"""X9: email_verified must default to False, not True."""
import inspect


def test_email_verified_defaults_to_false():
    """X9: auth_service must default email_verified to False."""
    from app.services import auth_service
    
    source = inspect.getsource(auth_service)
    
    # Проверить, что COALESCE использует false
    assert "COALESCE(email_verified, false)" in source, \
        "SQL must use COALESCE(email_verified, false)"
    
    # Проверить, что .get() использует False как дефолт
    assert "user.get('email_verified', False)" in source, \
        "user.get must default to False"
    assert "data.get('email_verified', False)" in source, \
        "data.get must default to False"
    
    # Проверить, что НЕ используется True как дефолт
    assert "email_verified', True)" not in source, \
        "email_verified must not default to True"
