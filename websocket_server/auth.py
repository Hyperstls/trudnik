"""Аутентификация для WebSocket-сервера. Использует WEBSOCKET_JWT_SECRET."""
import logging
import os
import redis as _redis
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger(__name__)

# ВАЖНО: использовать WEBSOCKET_JWT_SECRET, НЕ SECRET_KEY
SECRET_KEY = os.environ.get("WEBSOCKET_JWT_SECRET", "")
JWT_ALGORITHM = "HS256"

_redis_client = None

def _get_redis():
    """Singleton Redis-клиент для проверки jti blacklist."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        _redis_client = _redis.from_url(
            os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
            decode_responses=True
        )
        _redis_client.ping()
    except Exception:
        _redis_client = None
    return _redis_client

def verify_token(token: str) -> dict | None:
    if not SECRET_KEY:
        logger.error("WEBSOCKET_JWT_SECRET not set — rejecting all WS connections")
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if "user_id" not in payload:
            logger.warning("JWT-токен не содержит user_id")
            return None
        jti = payload.get('jti')
        if jti:
            r = _get_redis()
            if r is None:
                logger.error("Redis unavailable, jti check failed — token rejected")
                return None
            try:
                if r.exists(f'jti_blacklist:{jti}'):
                    logger.warning('Rejected blacklisted jti: %s', jti)
                    return None
            except Exception:
                logger.error("Redis error during jti blacklist check — token rejected")
                return None
        return payload
    except ExpiredSignatureError:
        logger.warning("JWT-токен просрочен")
        return None
    except InvalidTokenError as exc:
        logger.warning(f"Невалидный JWT-токен: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Неожиданная ошибка: {exc}")
        return None
