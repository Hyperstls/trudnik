"""Сервис CAPTCHA через Yandex SmartCaptcha (fail-closed).

Замена Cloudflare Turnstile (2026-08): резидентный РФ-сервис, исключает
трансграничную передачу ПДн (ст. 12 152-ФЗ) — см. docs/rkn_notification_fill.md.

Ключи: SMARTCAPTCHA_CLIENT_KEY (sitekey, публичный) + SMARTCAPTCHA_SERVER_KEY
(secret, только сервер). Форма отправляет hidden-input `smart-token`.
"""
import logging
import os

import requests as _requests

logger = logging.getLogger(__name__)

# Endpoint серверной проверки токена (Yandex Cloud, РФ).
_SMARTCAPTCHA_VALIDATE_URL = 'https://smartcaptcha.yandexcloud.net/validate'


def verify_captcha(token: str, ip: str | None = None) -> bool:
    """Проверить CAPTCHA токен через Yandex SmartCaptcha API.

    Fail-closed: если SMARTCAPTCHA_SERVER_KEY не задан или API недоступен —
    возвращает False.
    """
    secret = os.environ.get('SMARTCAPTCHA_SERVER_KEY', '')
    if not secret:
        logger.warning('captcha: SMARTCAPTCHA_SERVER_KEY not configured, rejecting')
        return False
    if not token:
        return False
    data = {'secret': secret, 'token': token}
    if ip:
        data['ip'] = ip
    try:
        resp = _requests.post(_SMARTCAPTCHA_VALIDATE_URL, data=data, timeout=5)
        return resp.ok and resp.json().get('status', '') == 'ok'
    except Exception as e:
        logger.warning('captcha verify failed: %s', e, exc_info=True)
        return False


def render_captcha_widget() -> str:
    """HTML-виджет CAPTCHA."""
    site_key = os.environ.get('SMARTCAPTCHA_CLIENT_KEY', '')
    if not site_key:
        return ''
    return f'<div class="smart-captcha" data-sitekey="{site_key}"></div>'


def is_captcha_enabled() -> bool:
    """Включена ли капча (Yandex SmartCaptcha).

    True только когда заданы ОБА ключа (client + server) И мы не в тестовом режиме.
    Дев-окружение без ключей → False (формы работают без капчи, fail-open).
    Прод с ключами → True (капча обязательна, fail-closed при невалидном/пустом токене).
    """
    if os.environ.get('TESTING', '').lower() in ('1', 'true', 'yes'):
        return False
    return bool(os.environ.get('SMARTCAPTCHA_CLIENT_KEY') and os.environ.get('SMARTCAPTCHA_SERVER_KEY'))


def captcha_client_key() -> str:
    """Публичный клиентский ключ (sitekey) для рендера виджета (безопасно отдавать клиенту)."""
    return os.environ.get('SMARTCAPTCHA_CLIENT_KEY', '')


def verify_captcha_token(token: str, ip: str | None = None) -> bool:
    """Проверить токен SmartCaptcha (hidden-input `smart-token`).

    - Капча не включена (dev/no-keys): пропустить (вернуть True) — нет барьера.
    - Включена: fail-closed (невалидный/пустой токен или недоступность API → False).
    """
    if not is_captcha_enabled():
        return True
    return verify_captcha(token or '', ip=ip)
