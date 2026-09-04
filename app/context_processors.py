"""Контекст-процессоры Flask: inject_ws_config, inject_unread_notifications, inject_pending_invitations."""

import logging
import os
import time
import secrets
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from flask import current_app, g, request, session

from app.utils.redis_cache import redis_cache_get, redis_cache_set

logger = logging.getLogger(__name__)


# ── In-process кэш для контекст-процессоров (TTL 30 сек) ──
@dataclass
class _ContextCacheEntry:
    value: int = 0
    timestamp: float = 0.0


_context_cache: dict[str, _ContextCacheEntry] = {}
_CONTEXT_CACHE_TTL = 30  # секунд


def _get_cached_or_fetch(key: str, fetch_fn) -> int:
    """Простой in-process кэш с TTL 30 секунд.

    Args:
        key: ключ кэша.
        fetch_fn: callable без аргументов, возвращает int.

    Returns:
        Закешированное или свежее значение.
    """
    now = time.time()
    entry = _context_cache.get(key)
    if entry is not None and (now - entry.timestamp) < _CONTEXT_CACHE_TTL:
        return entry.value
    value = fetch_fn()
    _context_cache[key] = _ContextCacheEntry(value=value, timestamp=now)
    return value


def inject_ws_config() -> dict:
    """Добавляет WebSocket-конфигурацию во все шаблоны.

    JWT-токен для WS НЕ встраивается в HTML (XSS-риск: любой скрипт мог его
    прочитать). Клиент получает токен по запросу через защищённый эндпоинт
    /api/ws/token (см. app.blueprints.notifications.get_ws_token).
    """
    from app.config import Config
    config = {
        'wsUrl': Config.WEBSOCKET_PUBLIC_URL or os.environ.get('WEBSOCKET_URL', ''),
        'wsPort': os.environ.get('WEBSOCKET_PORT', '8001'),
        'pushEnabled': bool(os.environ.get('VAPID_PUBLIC_KEY', '')),
    }
    return {'trudnik_ws_config': config}


def inject_unread_notifications() -> dict:
    """Глобальная переменная для бейджа уведомлений во всех шаблонах.

    Кешируется в Redis (TTL 30 сек, общий для всех worker'ов) + in-process fallback.
    Исключает уведомления-приглашения (они на 👤+ иконке).
    """
    from app.utils import postgrest_request

    user_id = session.get('user_id')
    if user_id:
        redis_key = f'unread:{user_id}'
        # Проверяем Redis-кэш (общий для всех worker'ов)
        count = redis_cache_get(redis_key)
        if count is not None:
            return {'unread_notifications': count}

        # Redis-промах — запрашиваем БД и сохраняем в Redis
        def _fetch() -> int:
            resp = postgrest_request(
                'GET',
                f'notifications?user_id=eq.{user_id}&is_read=eq.false&select=id,type,message&limit=100'
            )
            if resp.ok:
                data = resp.json()
                if isinstance(data, list):
                    # Исключаем уведомления "Вас пригласили" (приглашения трудника)
                    non_inv = [
                        n for n in data
                        if 'вас пригласили' not in (n.get('message') or '').lower()
                    ]
                    return len(non_inv)
            return 0

        count = _get_cached_or_fetch(f'notif_{user_id}', _fetch)
        # Сохраняем в Redis для других worker'ов
        redis_cache_set(redis_key, count, ttl=30)
        return {'unread_notifications': count}
    return {'unread_notifications': 0}


def inject_pending_invitations() -> dict:
    """Счётчик непрочитанных приглашений для трудника.

    Кешируется in-process с TTL 30 секунд (per-worker).
    Использует postgrest_request с токеном пользователя вместо service_role.
    RLS-политика invitations разрешает SELECT для worker_id = auth.uid(),
    поэтому обход RLS не требуется.
    """
    from app.utils import postgrest_request

    user_id = session.get('user_id')
    logger.debug(
        '[INV_CTX] user_id=%s', str(user_id)[:12] if user_id else 'None'
    )
    # Мультирольность (2026-09-03): приглашения может получить любой
    # пользователь с worker_visibility=true — не только role='worker'.
    # Запрос идёт по worker_id текущего пользователя.
    if user_id:
        def _fetch() -> int:
            resp = postgrest_request(
                'GET',
                f'invitations?worker_id=eq.{user_id}&status=eq.pending&select=id&limit=100'
            )
            if resp.ok:
                data = resp.json()
                count = len(data) if isinstance(data, list) else 0
                logger.debug('[INV_CTX] query ok, count=%d', count)
            else:
                count = 0
                logger.error(
                    '[INV_CTX] query FAILED: status=%s body=%s',
                    resp.status_code, (resp.text or '')[:200]
                )
            return count

        count = _get_cached_or_fetch(f'inv_{user_id}', _fetch)
        return {'pending_invitations': count}
    logger.debug('[INV_CTX] skip: no user_id')
    return {'pending_invitations': 0}


def inject_worker_site_url() -> dict:
    """Добавляет URL сайта трудника (для TWA/Telegram Web App) во все шаблоны."""
    return {'worker_site_url': current_app.config.get('WORKER_SITE_URL', '')}


def inject_employer_subscription() -> dict:
    """Данные подписки работодателя для UI монетизации.

    Возвращает employer_subscription с полями tariff и jobs_remaining
    для работодателей, если MONETIZATION_ENABLED.
    Кешируется in-process с TTL 60 секунд.
    """
    from app.utils import postgrest_request

    user_id = session.get('user_id')
    role = session.get('role')

    if not (user_id and role == 'employer'):
        return {'employer_subscription': None}

    if not current_app.config.get('MONETIZATION_ENABLED', False):
        return {'employer_subscription': None}

    def _fetch():
        resp = postgrest_request(
            'GET',
            f'employer_subscriptions?employer_id=eq.{user_id}&select=tariff,jobs_remaining&limit=1'
        )
        if resp.ok:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0]
        # Если записи нет — возвращаем дефолт
        return {'tariff': 'Базовый', 'jobs_remaining': 3}

    sub = _get_cached_or_fetch(f'sub_{user_id}', _fetch)
    return {'employer_subscription': sub or {'tariff': 'Базовый', 'jobs_remaining': 3}}


def inject_global_user() -> dict:
    """Добавляет current_user_id во все шаблоны."""
    return {'current_user_id': session.get('user_id')}


def inject_csrf_token() -> dict:
    """Внедрение CSRF-токена во все шаблоны как строки."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return {'csrf_token': session.get('_csrf_token', '')}


def inject_csp_nonce() -> dict:
    """Внедрение CSP nonce во все шаблоны для inline-скриптов."""
    return {'csp_nonce': getattr(g, 'csp_nonce', '')}


def inject_current_year() -> dict:
    """Текущий год для футера (© ... Трудник) — чтобы не устаревал."""
    from datetime import datetime
    return {'current_year': datetime.now().year}


def inject_captcha_config() -> dict:
    """Публичная конфигурация капчи (Yandex SmartCaptcha) для шаблонов.

    captcha_enabled=True только если заданы ключи (прод); в dev виджет не рендерится.
    """
    try:
        from app.utils.captcha import is_captcha_enabled, captcha_client_key
        return {
            'captcha_enabled': is_captcha_enabled(),
            'captcha_client_key': captcha_client_key(),
        }
    except Exception:
        return {'captcha_enabled': False, 'captcha_client_key': ''}


def inject_sort_url() -> dict:
    """Хелпер для построения URL сортировки с сохранением остальных параметров."""

    def sort_url(sort_value):
        args = dict(request.args)
        # Заменяем sort и сбрасываем page
        args['sort'] = sort_value
        args.pop('page', None)
        if not args:
            return '?'
        return '?' + '&'.join(f'{quote(str(k))}={quote(str(v))}' for k, v in args.items())

    return {'sort_url': sort_url}


def register_context_processors(app):
    """Зарегистрировать все контекст-процессоры на Flask-приложении.

    Args:
        app: экземпляр Flask.
    """
    app.context_processor(inject_global_user)
    app.context_processor(inject_csrf_token)
    app.context_processor(inject_csp_nonce)
    app.context_processor(inject_ws_config)
    app.context_processor(inject_unread_notifications)
    app.context_processor(inject_pending_invitations)
    app.context_processor(inject_worker_site_url)
    app.context_processor(inject_employer_subscription)
    app.context_processor(inject_sort_url)
    app.context_processor(inject_captcha_config)
    app.context_processor(inject_current_year)
