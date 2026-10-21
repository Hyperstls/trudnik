import secrets
import time
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

import jwt
from flask import current_app, flash, redirect, session, url_for

from app.config import Config
from app.utils.rate_limit_decorator import rate_limit  # noqa: F401 — ре-экспорт для обратной совместимости

F = TypeVar('F', bound=Callable[..., Any])


def _get_session_validity(user_id: str) -> dict | None:
    """Единая сводка валидности сессии: {'exists', 'suspended', 'pwd_changed_at'}.

    Одна выборка profiles + один Redis-ключ `session_check:{user_id}` (TTL 60с).
    Возвращает None, если БД недоступна (CB open / ошибка сети) — вызывающий
    решает fail-closed. Кэшируется и «пользователь не найден» (exists=False) —
    негативная запись безопасна: сессии у несуществующего пользователя быть
    не может (сессия появляется только после регистрации).
    """
    from app.utils.redis_cache import get_cached, set_cached
    cache_key = f'session_check:{user_id}'
    cached = get_cached(cache_key)
    if cached is not None:
        return cached
    from app.utils import postgrest_admin_request as _pgadm, postgrest_request as _pgreq
    from app.utils.postgrest_client import is_circuit_open as _is_cb_open
    fields = 'id,password_changed_at,suspended'
    resp = _pgreq('GET', f'profiles?id=eq.{user_id}&select={fields}')
    if not (resp.ok and not _is_cb_open(resp)):
        resp = _pgadm('GET', f'profiles?id=eq.{user_id}&select={fields}')
    if not resp.ok or _is_cb_open(resp):
        return None  # БД недоступна
    rows = resp.json()
    if rows:
        row = rows[0]
        validity = {
            'exists': True,
            'suspended': bool(row.get('suspended')),
            'pwd_changed_at': row.get('password_changed_at'),
        }
    else:
        validity = {'exists': False, 'suspended': False, 'pwd_changed_at': None}
    set_cached(cache_key, validity, ttl=60)
    return validity


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
        # verify_exp=False: проверяем exp ВРУЧНУЮ ниже, чтобы успеть сделать
        # refresh (иначе jwt.decode выбросит ExpiredSignatureError и пользователь
        # разлогинится каждые 5 минут вместо тихого обновления токена).
        try:
            decoded = jwt.decode(token, Config.PGRST_JWT_SECRET, algorithms=['HS256'],
                                options={'verify_aud': False, 'verify_exp': False})
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
            
            # ── Единая проверка валидности сессии (2026-09, упрощение) ──
            # Раньше: 3 отдельных ветки (pwd_changed_at, user_exists, suspended)
            # с тремя кэш-ключами и 2–4 запросами на каждый запрос страницы.
            # Теперь: ОДНА выборка profiles (id+password_changed_at+suspended)
            # + один Redis-ключ `session_check:{user_id}` (TTL 60с).
            user_id = decoded.get('user_id') or decoded.get('sub')
            if user_id:
                validity = _get_session_validity(user_id)
                if validity is None:
                    # БД недоступна (CB open / network) — fail-closed: 503 без
                    # разлогина (TC-087). Шаблон НЕ рендерим: рендер дёргает
                    # context-процессоры, которые снова упадут в ту же БД.
                    from flask import request as _req, jsonify as _jsonify
                    if _req.path.startswith('/api/') or _req.accept_mimetypes.best == 'application/json':
                        return _jsonify({'error': 'Сервис временно недоступен. Повторите позже.'}), 503
                    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
                            '<title>Сервис недоступен</title></head><body style="font-family:sans-serif;'
                            'max-width:32rem;margin:4rem auto;text-align:center">'
                            '<h1>Сервис временно недоступен</h1>'
                            '<p>База данных не отвечает. Попробуйте через минуту — ваша сессия сохранена.</p>'
                            '<p><a href="/">Обновить страницу</a></p></body></html>'), 503
                if not validity['exists']:
                    # БД подтвердила: пользователя нет (удалён)
                    session.clear()
                    return redirect(url_for('auth.login'))
                if validity['suspended']:
                    session.clear()
                    flash('Ваш аккаунт временно приостановлен. Если это ошибка — обратитесь в поддержку.', 'danger')
                    return redirect(url_for('auth.login'))
                # Инвалидация токенов при смене пароля (B10)
                token_pwd_changed = decoded.get('pwd_changed_at')
                profile_pwd_changed = validity['pwd_changed_at']
                if token_pwd_changed and profile_pwd_changed:
                    if str(profile_pwd_changed) != str(token_pwd_changed):
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
            from app.utils import (
                postgrest_admin_request as _pgadm,
                postgrest_request as _pgreq,
                is_circuit_open as _is_open,
            )
            # Пробуем пользовательский запрос (через RLS)
            resp = _pgreq('GET', f'profiles?id=eq.{session["user_id"]}&select=role')

            # Fallback: если пользовательский запрос не удался — пробуем через service_role
            if not resp.ok:
                resp = _pgadm('GET', f'profiles?id=eq.{session["user_id"]}&select=role')

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
                            flash('Доступ запрещён. Требуются права администратора.', 'danger')
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
        flash('Доступ запрещён. Требуются права администратора.', 'danger')
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
            flash('Доступ запрещён. Требуются права работодателя.', 'danger')
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
            flash('Доступ запрещён. Требуются права работника.', 'danger')
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
                flash(f'Произошла ошибка: {str(e)}', 'danger')
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





