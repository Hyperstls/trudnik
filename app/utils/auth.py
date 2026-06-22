"""Аутентификация: refresh_access_token, get_user_role, get_user_profile."""

import logging
import time
from typing import Any, Dict, Optional

import jwt as pyjwt
from flask import current_app, session

from app.config import Config

logger = logging.getLogger(__name__)

PGRST_JWT_SECRET = Config.PGRST_JWT_SECRET


def refresh_access_token() -> bool:
    """Генерирует новый JWT для PostgREST из user_id в сессии.

    Достаточно наличия user_id в сессии для генерации свежего токена.
    """
    user_id = session.get('user_id')

    if not user_id:
        return False

    try:
        payload = {
            'role': 'authenticated',
            'user_id': str(user_id),
            'exp': int(time.time()) + 3600,  # 1 час
            'iat': int(time.time()),
        }
        token = pyjwt.encode(
            payload,
            PGRST_JWT_SECRET,
            algorithm='HS256'
        )
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

    from app.utils.supabase import postgrest_request

    resp = postgrest_request(
        'GET',
        f'profiles?id=eq.{session["user_id"]}&select=*'
    )
    if resp.ok and resp.json():
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
    return None
