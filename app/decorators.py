import secrets
import time
from functools import wraps
from typing import Any, Callable, TypeVar

import jwt
from flask import abort, flash, redirect, request, session, url_for

from app.utils import refresh_access_token, supabase_request

F = TypeVar('F', bound=Callable[..., Any])


def login_required(f: F) -> F:
    """Декоратор: требует аутентификации пользователя.

    Проверяет наличие access_token в сессии. При истечении токена
    пытается обновить его через refresh_token. Если не удаётся —
    очищает сессию и перенаправляет на login.

    Args:
        f: функция-обработчик маршрута.

    Returns:
        Декорированная функция с проверкой аутентификации.
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        token = session.get('access_token')
        if not token:
            return redirect(url_for('auth.login'))

        # Proactive check: не истёк ли токен?
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            exp = decoded.get('exp', 0)
            if time.time() > exp:
                # Токен истёк — пробуем обновить
                if session.get('refresh_token'):
                    if refresh_access_token():
                        return f(*args, **kwargs)
                session.clear()
                return redirect(url_for('auth.login'))
        except (jwt.DecodeError, jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            # Токен невалидный или не JWT — пропускаем, Supabase разберётся
            pass

        return f(*args, **kwargs)
    return decorated  # type: ignore[return-value]


def role_required(role: str) -> Callable[[F], F]:
    """Декоратор: требует определённую роль пользователя.

    Проверяет роль через запрос к profiles. Если роль не совпадает —
    показывает flash-сообщение и перенаправляет на индекс.

    Args:
        role: требуемая роль ('worker', 'employer', 'admin').

    Returns:
        Декоратор, проверяющий роль пользователя.
    """
    def decorator(f: F) -> F:
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any) -> Any:
            if 'access_token' not in session:
                return redirect(url_for('auth.login'))
            resp = supabase_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
            data = resp.json()
            if not data or not isinstance(data, list) or not data:
                flash('Ошибка проверки прав доступа', 'danger')
                return redirect(url_for('jobs.index'))
            if data[0].get('role') != role:
                flash('Доступ запрещён', 'danger')
                return redirect(url_for('jobs.index'))
            return f(*args, **kwargs)
        return decorated  # type: ignore[return-value]
    return decorator


