"""Унифицированный Redis-клиент для всего приложения.

Предоставляет ленивую инициализацию Redis-клиента с TTL-кешем.
При отсутствии Redis — graceful degradation (возврат None).
"""

import logging
import os

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
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
        # Проверяем соединение
        _redis_client.ping()
        logger.info('Redis client connected to %s', redis_url)
    except Exception:
        _redis_client = None
        logger.warning('Redis not available, using graceful degradation')
    return _redis_client
