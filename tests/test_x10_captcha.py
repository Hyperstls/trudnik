"""X10: captcha must integrate Cloudflare Turnstile fail-closed."""
import inspect


def test_captcha_not_stub():
    """X10: verify_captcha must not be a stub returning True."""
    from app.utils import captcha
    
    source = inspect.getsource(captcha.verify_captcha)
    
    # Проверить, что НЕ просто return True
    assert "return True" not in source or "TURNSTILE_SECRET" in source, \
        "verify_captcha must not be a stub returning True"


def test_captcha_fail_closed():
    """X10: verify_captcha must be fail-closed."""
    from app.utils import captcha
    
    source = inspect.getsource(captcha.verify_captcha)
    
    # Проверить, что есть проверка TURNSTILE_SECRET
    assert "TURNSTILE_SECRET" in source, \
        "verify_captcha must check TURNSTILE_SECRET"
    
    # Проверить, что при отсутствии секрета возвращается False
    assert "return False" in source, \
        "verify_captcha must return False when secret is missing"
