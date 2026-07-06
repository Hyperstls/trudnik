"""Redis-кэш для межпроцессного обмена (TTL 30 сек).

Используется контекст-процессорами, notification_service и другими модулями
для инвалидации кэша счётчиков. При отсутствии Redis — graceful degradation.
"""

import logging

from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_REDIS_CACHE_TTL = 30  # секунд


def redis_cache_get(key: str):
    """Получает значение из Redis-кэша.

    Args:
        key: ключ кэша.

    Returns:
        Значение (int) или None, если ключ не найден или Redis недоступен.
    """
    try:
        client = get_redis_client()
        if client is None:
            return None
        value = client.get(key)
        if value is not None:
            return int(value)
    except Exception as e:
        logger.warning('redis_cache_get failed for key=%s: %s', key, e, exc_info=True)
    return None


def redis_cache_set(key: str, value: int, ttl: int = _REDIS_CACHE_TTL):
    """Сохраняет значение в Redis-кэш с TTL.

    Args:
        key: ключ кэша.
        value: целочисленное значение.
        ttl: время жизни в секундах (по умолчанию 30).
    """
    try:
        client = get_redis_client()
        if client is not None:
            client.setex(key, ttl, value)
    except Exception as e:
        logger.warning('redis_cache_set failed for key=%s: %s', key, e, exc_info=True)


def redis_cache_delete(key: str):
    """Удаляет ключ из Redis-кэша.

    Args:
        key: ключ кэша.
    """
    try:
        client = get_redis_client()
        if client is not None:
            client.delete(key)
    except Exception as e:
        logger.warning('redis_cache_delete failed for key=%s: %s', key, e, exc_info=True)


def get_cached(key: str):
    """Получает значение из кэша (универсальная функция).

    Args:
        key: ключ кэша.

    Returns:
        Значение или None, если ключ не найден или Redis недоступен.
    """
    try:
        client = get_redis_client()
        if client is None:
            return None
        value = client.get(key)
        if value is not None:
            # Пытаемся декодировать как JSON, иначе возвращаем как строку
            try:
                import json
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value.decode('utf-8') if isinstance(value, bytes) else value
    except Exception as e:
        logger.warning('get_cached failed for key=%s: %s', key, e, exc_info=True)
    return None


def set_cached(key: str, value, ttl: int = 60):
    """Сохраняет значение в кэш с TTL (универсальная функция).

    Args:
        key: ключ кэша.
        value: значение для сохранения (будет сериализовано в JSON).
        ttl: время жизни в секундах (по умолчанию 60).
    """
    try:
        client = get_redis_client()
        if client is not None:
            import json
            serialized = json.dumps(value)
            client.setex(key, ttl, serialized)
    except Exception as e:
        logger.warning('set_cached failed for key=%s: %s', key, e, exc_info=True)
