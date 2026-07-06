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
BCRYPT_ROUNDS = 12


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


def generate_jwt(user_id, role, exp_seconds=300):
    """Каноническая генерация JWT-токена."""
    import uuid as _uuid
    jti = str(_uuid.uuid4())
    payload = {
        'sub': str(user_id),
        'role': 'authenticated',  # PostgreSQL role — всегда 'authenticated'
        'aud': 'authenticated',  # требуется PostgREST (PGRST_JWT_AUD)
        'app_role': role,  # 'worker', 'employer', 'admin' — для RLS
        'user_id': str(user_id),
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(seconds=exp_seconds),
        'jti': jti,
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
    token = _jwt_lib.encode(payload, secret, algorithm='HS256')

    # Сохраняем jti в Redis с TTL = expiration (для проверки при refresh)
    try:
        from app.utils.redis_client import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            redis_client.setex(f'jti:{jti}', exp_seconds, user_id)
    except Exception:
        pass

    return token


def refresh_access_token() -> bool:
    """Генерирует новый JWT для PostgREST из user_id в сессии.

    Достаточно наличия user_id в сессии для генерации свежего токена.
    Использует каноническую функцию generate_jwt().
    Роль берётся из сессии (session['role']), fallback — 'authenticated'.
    """
    user_id = session.get('user_id')

    if not user_id:
        return False

    try:
        # Проверяем, не заблокирован ли старый jti
        old_token = session.get('access_token', '')
        if old_token:
            try:
                old_payload = _jwt_lib.decode(
                    old_token, PGRST_JWT_SECRET, algorithms=['HS256'],
                    options={'verify_exp': False}
                )
                old_jti = old_payload.get('jti', '')
                if old_jti:
                    from app.utils.redis_client import get_redis_client
                    redis_client = get_redis_client()
                    if redis_client and redis_client.exists(f'jti_blacklist:{old_jti}'):
                        # jti в чёрном списке — токен отозван
                        session.clear()
                        return False
            except Exception:
                pass  # Невалидный старый токен — игнорируем, всё равно создаём новый

        # Используем реальную роль из сессии, fallback — 'authenticated'
        role = session.get('role') or session.get('user', {}).get('role', 'authenticated')
        token = generate_jwt(user_id, role)
        session['access_token'] = token
        session.modified = True
        return True
    except Exception:
        session.clear()
        return False


def login_user_session(user_id: str, role: str, email: str) -> None:
    """Сохранить данные пользователя в сессии после успешного логина."""
    session.permanent = True
    token = generate_jwt(user_id, role)
    session['access_token'] = token
    session['refresh_token'] = 'jwt'
    session['user_id'] = user_id
    session['role'] = role
    session['email'] = email
    
    # Извлекаем jti из токена и сохраняем в сессию для последующей инвалидации
    try:
        payload = _jwt_lib.decode(token, PGRST_JWT_SECRET, algorithms=['HS256'], 
                                  options={'verify_exp': False, 'verify_aud': False})
        session['jti'] = payload.get('jti')
    except Exception as e:
        logger.warning('Failed to extract jti from token: %s', e, exc_info=True)
    
    session.modified = True


def is_jti_blacklisted(jti: str) -> bool:
    """Проверить, находится ли jti в чёрном списке (отозванный токен).

    Args:
        jti: JWT ID токена.

    Returns:
        True если jti в blacklist (токен отозван), иначе False.
    """
    if not jti:
        return False
    try:
        from app.utils.redis_client import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            return bool(redis_client.exists(f'jti_blacklist:{jti}'))
    except Exception as e:
        logger.warning('is_jti_blacklisted Redis error: %s', e, exc_info=True)
    return False


def blacklist_jti(jti: str, ttl: int = 86400) -> None:
    """Добавить JTI в Redis blacklist.

    Args:
        jti: JWT ID токена.
        ttl: время жизни в секундах (по умолчанию 24 часа).
    """
    if not jti:
        return
    try:
        from app.utils.redis_client import get_redis_client
        redis_client = get_redis_client()
        if redis_client:
            redis_client.setex(f'jti_blacklist:{jti}', ttl, '1')
    except Exception as e:
        logger.warning('blacklist_jti failed: %s', e, exc_info=True)


def get_user_role() -> Optional[str]:
    """Получить роль текущего пользователя из сессии.

    Returns:
        'admin', 'employer', 'worker' или None.
    """
    return session.get('role')


def get_user_profile() -> Optional[Dict[str, Any]]:
    """Получить профиль текущего пользователя из PostgREST (Amvera). Supabase не используется (устарело).

    Returns:
        Словарь профиля или None.
    """
    if 'access_token' not in session:
        return None

    from app.utils.postgrest_client import postgrest_request

    resp = postgrest_request(
        'GET',
        f'profiles?id=eq.{session["user_id"]}&select=id,role,created_at,updated_at,is_self_employed,email_public,rating,full_name,photo_url,age,bio,city,experience,desired_payment,verification_status,total_reviews,skills,religion,religion_id,portfolio_link'
    )
    if resp.ok and resp.json():
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
    return None
