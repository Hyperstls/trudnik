"""
Модуль аутентификации для WebSocket-сервера.

Верифицирует JWT-токены, совместимые с Flask-приложением Trudnik,
используя тот же SECRET_KEY и алгоритм HS256.
"""

import logging
import os

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger(__name__)

# Секретный ключ, совместимый с Flask-приложением
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
# Алгоритм подписи JWT
JWT_ALGORITHM = "HS256"


def verify_token(token: str) -> dict | None:
    """
    Декодирует и проверяет JWT-токен.

    Args:
        token: JWT-строка из query-параметра ?token=...

    Returns:
        Словарь payload с ключом user_id при успехе, либо None при невалидном токене.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        # Проверяем наличие user_id в payload
        if "user_id" not in payload:
            logger.warning("JWT-токен не содержит user_id в payload")
            return None
        return payload
    except ExpiredSignatureError:
        logger.warning("JWT-токен просрочен")
        return None
    except InvalidTokenError as exc:
        logger.warning(f"Невалидный JWT-токен: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Неожиданная ошибка при верификации токена: {exc}")
        return None
