"""Унифицированный Redis-клиент для всего приложения.
 
Предоставляет ленивую thread-safe инициализацию Redis-клиента с double-check locking.
При отсутствии Redis — graceful degradation (возврат None).
"""
 
import logging
import os
from threading import Lock
 
logger = logging.getLogger(__name__)
 
_redis_client = None
_redis_lock = Lock()
 
 
def get_redis_client():
    """Ленивая thread-safe инициализация Redis-клиента (double-check locking).
 
    Returns:
        Redis-клиент или None, если Redis недоступен.
    """
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis as _redis_lib
            redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
            _redis_client = _redis_lib.from_url(redis_url, decode_responses=True)
            # Проверяем соединение
            _redis_client.ping()
            logger.info('Redis client connected to %s', redis_url)
        except Exception as e:
            _redis_client = None
            logger.warning('Redis not available, using graceful degradation: %s', e, exc_info=True)
    return _redis_client


# ═══════════════════════════════════════════════════════════════
# Account Lockout (C56)
# ═══════════════════════════════════════════════════════════════

def set_lockout(email: str, ttl_seconds: int = 900) -> bool:
    """Заблокировать аккаунт на указанное время (по умолчанию 15 минут).

    Args:
        email: email пользователя для блокировки.
        ttl_seconds: время блокировки в секундах (по умолчанию 900 = 15 минут).

    Returns:
        True если блокировка установлена, False при ошибке.
    """
    try:
        client = get_redis_client()
        if client is None:
            return False
        client.setex(f'lockout:{email}', ttl_seconds, '1')
        logger.info('Account lockout set for %s (%d seconds)', email, ttl_seconds)
        return True
    except Exception as e:
        logger.warning('Failed to set lockout for %s: %s', email, e)
        return False


def get_lockout(email: str) -> bool:
    """Проверить, заблокирован ли аккаунт.

    Args:
        email: email пользователя для проверки.

    Returns:
        True если аккаунт заблокирован, иначе False.
    """
    try:
        client = get_redis_client()
        if client is None:
            return False
        return client.exists(f'lockout:{email}') > 0
    except Exception as e:
        logger.warning('Failed to check lockout for %s: %s', email, e)
        return False


# ═══════════════════════════════════════════════════════════════
# JTI Blacklist (C56)
# ═══════════════════════════════════════════════════════════════

def add_to_jti_blacklist(jti: str, ttl: int = 3600) -> bool:
    """Добавить jti в чёрный список (отзыв токена).

    Args:
        jti: JWT ID токена для отзыва.
        ttl: время жизни записи в секундах (должно совпадать с expiration токена).

    Returns:
        True если jti добавлен в blacklist, False при ошибке.
    """
    try:
        client = get_redis_client()
        if client is None:
            return False
        client.setex(f'jti_blacklist:{jti}', ttl, '1')
        logger.info('JTI added to blacklist: %s (TTL=%d)', jti, ttl)
        return True
    except Exception as e:
        logger.warning('Failed to add jti to blacklist %s: %s', jti, e)
        return False


def is_jti_blacklisted(jti: str) -> bool:
    """Проверить, находится ли jti в чёрном списке.

    Args:
        jti: JWT ID токена для проверки.

    Returns:
        True если jti в чёрном списке, иначе False.
    """
    try:
        client = get_redis_client()
        if client is None:
            return False
        return client.exists(f'jti_blacklist:{jti}') > 0
    except Exception as e:
        logger.warning('Failed to check jti blacklist %s: %s', jti, e)
        return False
