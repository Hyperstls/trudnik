"""Yandex SmartCaptcha — серверная проверка (РФ, 152-ФЗ; паритет app/utils/captcha.py).

Капча включена, когда заданы ОБА ключа (SMARTCAPTCHA_SERVER_KEY + client в
контексте) и не установлена DJANGO_CAPTCHA_DISABLED=1. Включена → fail-closed:
любая ошибка проверки = отказ.
"""
import json
import logging
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

VALIDATE_URL = "https://smartcaptcha.yandexcloud.net/validate"


def captcha_enabled() -> bool:
    if os_env_disabled():
        return False
    return bool(getattr(settings, "SMARTCAPTCHA_SERVER_KEY", ""))


def os_env_disabled() -> bool:
    import os

    return os.getenv("DJANGO_CAPTCHA_DISABLED") == "1"


def verify_captcha_token(token: str) -> bool:
    """fail-closed: нет токена/ключа, ошибка сети, не success → False."""
    if not captcha_enabled():
        return True  # выключена конфигурацией (dev/тесты)
    if not token:
        return False
    data = json.dumps(
        {"secret": settings.SMARTCAPTCHA_SERVER_KEY, "token": token}
    ).encode()
    req = urllib.request.Request(
        VALIDATE_URL, data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
            return payload.get("status") == "ok"
    except Exception:
        logger.warning("smartcaptcha verify failed", exc_info=True)
        return False
