import secrets
import time
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

import jwt
from flask import abort, current_app, flash, redirect, session, url_for

from app.config import Config
from app.utils.rate_limit_decorator import rate_limit  # noqa: F401 — ре-экспорт для обратной совместимости

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
            decoded = jwt.decode(token, Config.PGRST_JWT_SECRET, algorithms=['HS256'])
            exp = decoded.get('exp', 0)
            if time.time() > exp:
                # Токен истёк — пробуем обновить
                if session.get('refresh_token'):
                    from app.utils import refresh_access_token as _refresh_token
                    if _refresh_token():
                        return f(*args, **kwargs)
                session.clear()
                return redirect(url_for('auth.login'))
            
            # X7: Проверка jti-blacklist (отозванные токены)
            jti = decoded.get('jti')
            if jti:
                from app.utils.auth import is_jti_blacklisted
                if is_jti_blacklisted(jti):
                    session.clear()
                    return redirect(url_for('auth.login'))
            
            # B5: Проверка существования пользователя в profiles (кэш 60 сек)
            user_id = decoded.get('user_id') or decoded.get('sub')
            if user_id:
                cache_key = f'user_exists:{user_id}'
                from app.utils.redis_cache import get_cached, set_cached
                user_exists = get_cached(cache_key)
                if user_exists is None:
                    from app.utils import postgrest_request as _pgreq
                    resp = _pgreq('GET', f'profiles?id=eq.{user_id}&select=id')
                    user_exists = resp.ok and bool(resp.json())
                    set_cached(cache_key, user_exists, ttl=60)
                if not user_exists:
                    session.clear()
                    return redirect(url_for('auth.login'))
        except (jwt.DecodeError, jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            # Токен невалидный — очищаем сессию и перенаправляем на login
            session.clear()
            return redirect(url_for('auth.login'))

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
            from app.utils import postgrest_request as _pgreq, is_circuit_open as _is_open
            resp = _pgreq('GET', f'profiles?id=eq.{session["user_id"]}&select=role')

            # Проверка на Circuit Breaker OPEN
            if _is_open(resp):
                flash('Сервис временно недоступен. Пожалуйста, попробуйте позже.', 'warning')
                return redirect(url_for('jobs.index'))

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


# ============================================================
# Auth & Permission Decorators
# ============================================================

def get_user_profile():
    """Получить профиль текущего пользователя из PostgREST (Amvera) — делегирует в app.utils.auth. Supabase не используется."""
    from app.utils.auth import get_user_profile as _get_profile
    return _get_profile()


def _is_authenticated():
    """Проверить аутентификацию через сессию (без flask_login). Supabase не используется — проект на Amvera."""
    return 'access_token' in session and 'user_id' in session


def admin_required(f):
    """Require admin role — с DB-перепроверкой через postgrest_admin_request."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('auth.login'))
        # DB-перепроверка: запрашиваем реальную роль из БД через admin-клиент
        user_id = session.get('user_id')
        if user_id:
            from app.utils import postgrest_admin_request
            try:
                resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=role')
                if resp.ok and resp.json():
                    data = resp.json()
                    if isinstance(data, list) and data:
                        db_role = data[0].get('role', '')
                        if db_role != 'admin':
                            flash('Доступ запрещён. Требуются права администратора.', 'error')
                            return redirect(url_for('jobs.index'))
                        return f(*args, **kwargs)
                # X8: DB-запрос не удался или данные невалидные — fail-closed
                flash('Сервис недоступен', 'danger')
                return redirect(url_for('jobs.index'))
            except Exception as e:
                # X8: fail-closed — при ошибке БД блокируем доступ
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning('admin_required DB error: %s', e, exc_info=True)
                flash('Сервис недоступен', 'danger')
                return redirect(url_for('jobs.index'))
        # Если user_id не найден в сессии — блокируем
        flash('Доступ запрещён. Требуются права администратора.', 'error')
        return redirect(url_for('jobs.index'))
    return decorated_function


def employer_required(f):
    """Require employer role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('auth.login'))
        profile = get_user_profile()
        if not profile or profile.get('role') != 'employer':
            flash('Доступ запрещён. Требуются права работодателя.', 'error')
            return redirect(url_for('jobs.index'))
        return f(*args, **kwargs)
    return decorated_function


def worker_required(f):
    """Require worker role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('auth.login'))
        profile = get_user_profile()
        if not profile or profile.get('role') != 'worker':
            flash('Доступ запрещён. Требуются права работника.', 'error')
            return redirect(url_for('jobs.index'))
        return f(*args, **kwargs)
    return decorated_function


def handle_errors(redirect_endpoint='jobs.index'):
    """Unified error handler for blueprint routes.
    
    Usage:
        @bp.route('/some-path')
        @handle_errors('main.index')
        def some_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                current_app.logger.error(f"Error in {f.__name__}: {e}", exc_info=True)
                flash(f'Произошла ошибка: {str(e)}', 'error')
                return redirect(url_for(redirect_endpoint))
        return decorated_function
    return decorator


# ============================================================
# UUID Validation Decorator
# ============================================================

def validate_uuid(*param_names: str):
    """Проверяет, что указанные параметры маршрута являются валидными UUID.

    При невалидном UUID показывает flash-сообщение и перенаправляет на индекс.

    Args:
        *param_names: имена параметров маршрута для проверки (например, 'job_id', 'user_id').

    Returns:
        Декоратор, проверяющий UUID-параметры.
    """
    def decorator(f: F) -> F:
        @wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for name in param_names:
                if name in kwargs:
                    try:
                        uuid.UUID(kwargs[name])
                    except (ValueError, AttributeError):
                        flash(f'Некорректный идентификатор: {name}', 'danger')
                        return redirect(url_for('jobs.index'))
            return f(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator





