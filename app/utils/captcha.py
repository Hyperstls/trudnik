"""Сервис CAPTCHA через Cloudflare Turnstile (fail-closed)."""
import logging
import os

import requests as _requests

logger = logging.getLogger(__name__)


def verify_captcha(token: str) -> bool:
    """Проверить CAPTCHA токен через Cloudflare Turnstile API.
    
    Fail-closed: если TURNSTILE_SECRET не задан или API недоступен — возвращает False.
    """
    secret = os.environ.get('TURNSTILE_SECRET', '')
    if not secret:
        logger.warning('captcha: TURNSTILE_SECRET not configured, rejecting')
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
