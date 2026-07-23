"""Сервис CAPTCHA через Cloudflare Turnstile (fail-closed)."""
import logging
import os

import requests as _requests

logger = logging.getLogger(__name__)


def verify_captcha(token: str) -> bool:
    """Проверить CAPTCHA токен через Cloudflare Turnstile API.
    
    Fail-closed: если TURNSTILE_SECRET_KEY не задан или API недоступен — возвращает False.
    """
    secret = os.environ.get('TURNSTILE_SECRET_KEY', '')
    if not secret:
        logger.warning('captcha: TURNSTILE_SECRET_KEY not configured, rejecting')
        return False
    if not token:
        return False
    try:
        resp = _requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data={'secret': secret, 'response': token},
            timeout=5
        )
        return resp.ok and resp.json().get('success', False)
    except Exception as e:
        logger.warning('captcha verify failed: %s', e, exc_info=True)
        return False


def render_captcha_widget() -> str:
    """HTML-виджет CAPTCHA."""
    site_key = os.environ.get('TURNSTILE_SITE_KEY', '')
    if not site_key:
        return ''
    return f'<div class="cf-turnstile" data-sitekey="{site_key}"></div>'


def is_captcha_enabled() -> bool:
    """Включена ли капча (Cloudflare Turnstile).

    True только когда заданы ОБА ключа (site + secret) И мы не в тестовом режиме.
    Дев-окружение без ключей → False (формы работают без капчи, fail-open).
    Прод с ключами → True (капча обязательна, fail-closed при невалидном/пустом токене).
    """
    if os.environ.get('TESTING', '').lower() in ('1', 'true', 'yes'):
        return False
    return bool(os.environ.get('TURNSTILE_SITE_KEY') and os.environ.get('TURNSTILE_SECRET_KEY'))


def turnstile_site_key() -> str:
    """Публичный site key для рендера виджета (безопасно отдавать клиенту)."""
    return os.environ.get('TURNSTILE_SITE_KEY', '')


def verify_captcha_token(token: str) -> bool:
    """Проверить токен Turnstile.

    - Капча не включена (dev/no-keys): пропустить (вернуть True) — нет барьера.
    - Включена: fail-closed (невалидный/пустой токен или недоступность CF → False).
    """
    if not is_captcha_enabled():
        return True
    return verify_captcha(token or '')
