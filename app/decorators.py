import secrets
import time
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

import jwt
from flask import abort, current_app, flash, jsonify, redirect, request, session, url_for

from app.config import Config
from app.utils import refresh_access_token, postgrest_request

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
            resp = postgrest_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')

            # Проверка на Circuit Breaker OPEN
            if hasattr(resp, 'circuit_open') and resp.circuit_open:
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
    """Получить профиль текущего пользователя из Supabase."""
    if 'access_token' not in session:
        return None
    resp = postgrest_request('GET', f'profiles?id=eq.{session["user_id"]}&select=*')
    if resp.ok and resp.json():
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
    return None


def _is_authenticated():
    """Проверить аутентификацию через сессию Supabase (без flask_login)."""
    return 'access_token' in session and 'user_id' in session


def admin_required(f):
    """Require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('auth.login'))
        profile = get_user_profile()
        if not profile or profile.get('role') != 'admin':
            flash('Доступ запрещён. Требуются права администратора.', 'error')
            return redirect(url_for('jobs.index'))
        return f(*args, **kwargs)
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


# ============================================================
# Rate Limiting (Redis-based — общий для всех gunicorn worker'ов)
# ============================================================

_RATE_WINDOW = 60           # секунд
_RATE_MAX_REQUESTS = 10     # запросов в окне


def rate_limit(f: F) -> F:
    """Декоратор: ограничение частоты POST-запросов через Redis.

    Использует Redis INCR + EXPIRE вместо in-memory словаря,
    что корректно работает с несколькими gunicorn worker'ами.

    Ключ: ratelimit:{endpoint}:{user_id}

    Args:
        f: функция-обработчик маршрута.

    Returns:
        Декорированная функция с rate limiting (10 попыток в минуту).
    """
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> Any:
        if request.method != 'POST':
            return f(*args, **kwargs)
        if current_app.config.get('TESTING'):
            return f(*args, **kwargs)

        user_id = session.get('user_id') or request.remote_addr or 'anonymous'
        endpoint = request.path
        key = f"ratelimit:{endpoint}:{user_id}"

        try:
            redis_client = getattr(current_app, 'redis', None)
            if redis_client is None:
                # Redis недоступен — разрешаем запрос (graceful degradation)
                return f(*args, **kwargs)

            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, _RATE_WINDOW)

            if current > _RATE_MAX_REQUESTS:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                   'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': 'Слишком много попыток. Подождите минуту.'}), 429
                flash('Слишком много попыток. Подождите минуту.', 'danger')
                return redirect(url_for('auth.login'))
        except Exception:
            # Ошибка Redis — разрешаем запрос (graceful degradation)
            pass

        return f(*args, **kwargs)
    return decorated  # type: ignore[return-value]


