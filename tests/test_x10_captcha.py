"""X10: captcha must integrate Yandex SmartCaptcha fail-closed.

(Замена Cloudflare Turnstile 2026-08: резидентный РФ-сервис, 152-ФЗ ст. 12 —
исключение трансграничной передачи ПДн.)
"""
import inspect


def test_captcha_not_stub():
    """X10: verify_captcha must not be a stub returning True."""
    from app.utils import captcha

    source = inspect.getsource(captcha.verify_captcha)

    # Проверить, что НЕ просто return True
    assert "return True" not in source or "SMARTCAPTCHA_SERVER" in source, \
        "verify_captcha must not be a stub returning True"


def test_captcha_fail_closed():
    """X10: verify_captcha must be fail-closed."""
    from app.utils import captcha

    source = inspect.getsource(captcha.verify_captcha)

    # Проверить, что есть проверка SMARTCAPTCHA_SERVER_KEY
    assert "SMARTCAPTCHA_SERVER" in source, \
        "verify_captcha must check SMARTCAPTCHA_SERVER_KEY"

    # Проверить, что при отсутствии секрета возвращается False
    assert "return False" in source, \
        "verify_captcha must return False when secret is missing"


def test_captcha_uses_russian_endpoint():
    """X10: валидация токена — только через endpoint Yandex Cloud (РФ)."""
    from app.utils import captcha

    assert captcha._SMARTCAPTCHA_VALIDATE_URL == 'https://smartcaptcha.yandexcloud.net/validate'
    source = inspect.getsource(captcha)
    assert 'cloudflare.com' not in source, \
        'Cloudflare Turnstile должен быть полностью удалён (трансграничная передача)'


def test_widget_uses_client_key():
    """X10: публичный ключ виджета — SMARTCAPTCHA_CLIENT_KEY (не секрет)."""
    from app.utils import captcha

    source = inspect.getsource(captcha.captcha_client_key)
    assert 'SMARTCAPTCHA_CLIENT_KEY' in source
