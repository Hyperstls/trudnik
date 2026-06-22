"""Контекст-процессоры Flask: inject_ws_config, inject_unread_notifications, inject_pending_invitations."""

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from flask import current_app, session

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


# ── Redis-кэш для контекст-процессоров (TTL 30 сек) ──
# Глобальный кэш между worker'ами через Redis.
# При отсутствии Redis — graceful degradation (возврат None).
_redis_client = None
_REDIS_CACHE_TTL = 30  # секунд


def _get_redis_client():
    """Ленивая инициализация Redis-клиента.

    Returns:
        Redis-клиент или None, если Redis недоступен.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis as _redis_lib
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        _redis_client = _redis_lib.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
    except Exception:
        _redis_client = None
    return _redis_client


def _redis_cache_get(key: str):
    """Получает значение из Redis-кэша.

    Args:
        key: ключ кэша.

    Returns:
        Значение (int) или None, если ключ не найден или Redis недоступен.
    """
    try:
        client = _get_redis_client()
        if client is None:
            return None
        value = client.get(key)
        if value is not None:
            return int(value)
    except Exception:
        pass
    return None


def _redis_cache_set(key: str, value: int, ttl: int = _REDIS_CACHE_TTL):
    """Сохраняет значение в Redis-кэш с TTL.

    Args:
        key: ключ кэша.
        value: целочисленное значение.
        ttl: время жизни в секундах (по умолчанию 30).
    """
    try:
        client = _get_redis_client()
        if client is not None:
            client.setex(key, ttl, value)
    except Exception:
        pass


def _redis_cache_delete(key: str):
    """Удаляет ключ из Redis-кэша.

    Args:
        key: ключ кэша.
    """
    try:
        client = _get_redis_client()
        if client is not None:
            client.delete(key)
    except Exception:
        pass


def inject_ws_config() -> dict:
    """Добавляет WebSocket-конфигурацию и JWT-токен во все шаблоны."""
    config = {
        'wsUrl': os.environ.get('WEBSOCKET_URL', ''),
        'wsPort': os.environ.get('WEBSOCKET_PORT', '8001'),
        'pushEnabled': bool(os.environ.get('VAPID_PUBLIC_KEY', '')),
        'jwtToken': ''
    }

    # Генерируем JWT-токен для аутентифицированных пользователей
    user_id = session.get('user_id')
    if user_id:
        try:
            import jwt as pyjwt
            token = pyjwt.encode(
                {
                    'user_id': str(user_id),
                    'exp': datetime.now(timezone.utc) + timedelta(days=7)
                },
                current_app.config['SECRET_KEY'],
                algorithm='HS256'
            )
            config['jwtToken'] = token
        except Exception:
            pass  # Любая ошибка — не фатально

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
        count = _redis_cache_get(redis_key)
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
        _redis_cache_set(redis_key, count, ttl=30)
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
    role = session.get('role')
    logger.debug(
        '[INV_CTX] user_id=%s role=%s',
        str(user_id)[:12] if user_id else 'None', role
    )
    if user_id and role == 'worker':
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
    logger.debug('[INV_CTX] skip: no user_id or not worker')
    return {'pending_invitations': 0}


def register_context_processors(app):
    """Зарегистрировать все контекст-процессоры на Flask-приложении.

    Args:
        app: экземпляр Flask.
    """
    app.context_processor(inject_ws_config)
    app.context_processor(inject_unread_notifications)
    app.context_processor(inject_pending_invitations)
