"""Аутентификация: generate_jwt, refresh_access_token, get_user_role, get_user_profile, check_password, hash_password."""

import logging
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
import jwt as _jwt_lib
from flask import current_app, session

from app.config import Config

logger = logging.getLogger(__name__)

PGRST_JWT_SECRET = Config.PGRST_JWT_SECRET

# Константа: количество раундов bcrypt, совпадает с gen_salt('bf') по умолчанию в PostgreSQL
BCRYPT_ROUNDS = 6


def check_password(password: str, stored_hash: str) -> bool:
    """Проверить пароль против Blowfish-хеша (из PostgreSQL crypt() или Python bcrypt).

    Совместима с хешами формата $2a$ (PostgreSQL gen_salt('bf')) и $2b$ (Python bcrypt).
    Оба используют алгоритм Blowfish, разница только в префиксе версии.

    Args:
        password: пароль открытым текстом.
        stored_hash: хеш из БД (формат $2a$06$... или $2b$06$...).

    Returns:
        True если пароль совпадает с хешем, иначе False.
    """
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(
            password.encode('utf-8'),
            stored_hash.encode('utf-8')
        )
    except (ValueError, TypeError, UnicodeError) as e:
        logger.warning('check_password failed: %s', e)
        return False


def hash_password(password: str) -> str:
    """Сгенерировать Blowfish-хеш пароля, совместимый с PostgreSQL crypt().

    Использует bcrypt с 6 раундами (как gen_salt('bf') по умолчанию в PostgreSQL).
    Генерирует хеш с префиксом $2b$ (Python bcrypt), который проверяется
    PostgreSQL функцией crypt() без проблем — pgcrypto понимает оба префикса.

    Args:
        password: пароль открытым текстом.

    Returns:
        Blowfish-хеш в формате $2b$06$<salt><hash>.
    """
    if not password:
        raise ValueError('Пароль не может быть пустым')
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode('utf-8')


def generate_jwt(user_id, role, exp_seconds=3600):
    """Каноническая генерация JWT-токена."""
    payload = {
        'sub': str(user_id),
        'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(seconds=exp_seconds),
        'jti': secrets.token_hex(8)
    }
    # Приоритет: 1) модульная переменная PGRST_JWT_SECRET (Config.PGRST_JWT_SECRET),
    # 2) current_app.config (может быть пустой строкой), 3) os.environ (runtime fallback).
    # SECRET_KEY НЕ ИСПОЛЬЗУЕТСЯ — он не совпадает с секретом PostgREST.
    import os as _os
    secret = PGRST_JWT_SECRET
    if not secret:
        secret = current_app.config.get('PGRST_JWT_SECRET') or _os.environ.get('PGRST_JWT_SECRET', '')
    if not secret:
        current_app.logger.error(
            'PGRST_JWT_SECRET is not configured! JWT signing will fail. '
            'Set PGRST_JWT_SECRET env var or Config.PGRST_JWT_SECRET.'
        )
        raise RuntimeError(
            'PGRST_JWT_SECRET is not configured. '
            'JWT tokens must be signed with the same secret as PostgREST.'
        )
    current_app.logger.info(
        'JWT: signing with secret prefix=%s... (%d bytes)',
        secret[:8], len(secret.encode('utf-8'))
    )
    return _jwt_lib.encode(payload, secret, algorithm='HS256')


def refresh_access_token() -> bool:
    """Генерирует новый JWT для PostgREST из user_id в сессии.

    Достаточно наличия user_id в сессии для генерации свежего токена.
    Использует каноническую функцию generate_jwt().

    ВАЖНО: Всегда использует роль trudnikapp (текущий пользователь БД PostgREST),
    т.к. SET ROLE authenticated/anon требует SUPERUSER, которого нет на проде.
    """
    user_id = session.get('user_id')

    if not user_id:
        return False

    try:
        # Используем trudnikapp — аутентификатор PostgREST (SET ROLE = no-op).
        # Не используем session['role'] (authenticated/worker/employer/admin),
        # т.к. на проде нет SUPERUSER для GRANT этих ролей.
        token = generate_jwt(user_id, 'trudnikapp')
        session['access_token'] = token
        session.modified = True
        return True
    except Exception:
        session.clear()
        return False


def get_user_role() -> Optional[str]:
    """Получить роль текущего пользователя из сессии.

    Returns:
        'admin', 'employer', 'worker' или None.
    """
    return session.get('role')


def get_user_profile() -> Optional[Dict[str, Any]]:
    """Получить профиль текущего пользователя из Supabase.

    Returns:
        Словарь профиля или None.
    """
    if 'access_token' not in session:
        return None

    from app.utils.postgrest_client import postgrest_request

    resp = postgrest_request(
        'GET',
        f'profiles?id=eq.{session["user_id"]}&select=*'
    )
    if resp.ok and resp.json():
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
    return None
