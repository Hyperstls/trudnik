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
            
            # B10: Проверка password_changed_at (инвалидация токенов при смене пароля)
            # Используем postgrest_admin_request (service_role) для надёжности —
            # пользовательский JWT может быть невалидным или PostgREST может быть недоступен.
            token_pwd_changed = decoded.get('pwd_changed_at')
            if token_pwd_changed:
                user_id = decoded.get('user_id') or decoded.get('sub')
                if user_id:
                    cache_key = f'pwd_changed:{user_id}'
                    from app.utils.redis_cache import get_cached, set_cached
                    profile_pwd_changed = get_cached(cache_key)
                    if profile_pwd_changed is None:
                        from app.utils import postgrest_admin_request as _pgadm, postgrest_request as _pgreq
                        # Пробуем через service_role (надёжнее — обходит RLS)
                        resp = _pgadm('GET', f'profiles?id=eq.{user_id}&select=password_changed_at')
                        if not (resp.ok and resp.json()):
                            # Fallback: пользовательский запрос
                            resp = _pgreq('GET', f'profiles?id=eq.{user_id}&select=password_changed_at')
                        if resp.ok and resp.json():
                            data = resp.json()
                            profile_data = data[0] if isinstance(data, list) and data else data
                            profile_pwd_changed = profile_data.get('password_changed_at') if isinstance(profile_data, dict) else None
                            if profile_pwd_changed is not None:
                                set_cached(cache_key, profile_pwd_changed, ttl=60)
                    
                    # Сравниваем: если в профиле пароль изменён ПОСЛЕ выпуска токена, токен недействителен
                    if profile_pwd_changed:
                        from datetime import datetime
                        try:
                            # Нормализуем оба значения к datetime
                            if isinstance(profile_pwd_changed, str):
                                profile_dt = datetime.fromisoformat(profile_pwd_changed.replace('Z', '+00:00'))
                            else:
                                profile_dt = profile_pwd_changed
                            
                            if isinstance(token_pwd_changed, str):
                                token_dt = datetime.fromisoformat(token_pwd_changed.replace('Z', '+00:00'))
                            else:
                                token_dt = token_pwd_changed
                            
                            # Если пароль изменён после выпуска токена - инвалидируем
                            if profile_dt > token_dt:
                                session.clear()
                                return redirect(url_for('auth.login'))
                        except (ValueError, TypeError):
                            # Если не удалось распарсить даты - используем строковое сравнение
                            if str(profile_pwd_changed) != str(token_pwd_changed):
                                session.clear()
                                return redirect(url_for('auth.login'))
            
            # B5: Проверка существования пользователя в profiles (кэш 60 сек)
            # Используем postgrest_admin_request (service_role) вместо пользовательского JWT,
            # чтобы проверка работала даже при недоступности/сбоях PostgREST у пользователя.
            # Кэшируем ТОЛЬКО положительный результат — отрицательный не кэшируется,
            # чтобы временный сбой PostgREST не блокировал пользователя на 60 секунд.
            user_id = decoded.get('user_id') or decoded.get('sub')
            if user_id:
                cache_key = f'user_exists:{user_id}'
                from app.utils.redis_cache import get_cached, set_cached
                user_exists = get_cached(cache_key)
                if user_exists is None:
                    from app.utils import postgrest_admin_request as _pgadm, postgrest_request as _pgreq
                    from app.utils.postgrest_client import is_circuit_open as _is_cb_open
                    # Пробуем пользовательский запрос (через RLS — быстрее)
                    resp = _pgreq('GET', f'profiles?id=eq.{user_id}&select=id')
                    db_reachable = resp.ok
                    if resp.ok and resp.json():
                        user_exists = True
                    else:
                        # Fallback: запрос через service_role (обходит RLS)
                        resp2 = _pgadm('GET', f'profiles?id=eq.{user_id}&select=id')
                        db_reachable = db_reachable or (resp2.ok and not _is_cb_open(resp2))
                        user_exists = resp2.ok and bool(resp2.json())
                    # Кэшируем ТОЛЬКО True (положительный результат).
                    # False не кэшируем — временный сбой PostgREST не должен
                    # блокировать пользователя на 60 секунд.
                    if user_exists:
                        set_cached(cache_key, True, ttl=60)
                # Решение по сессии:
                # - Если БД подтвердила, что пользователя НЕТ (200 + пусто) — закрываем доступ.
                # - Если PostgREST недоступен (CB open / network error / role error) —
                #   НЕ выкидываем пользователя (fail-open): он аутентифицирован валидным JWT,
                #   логин прошёл через прямой SQL. Временный сбой API не должен разлогинивать.
                if not user_exists:
                    if db_reachable:
                        # БД доступна и подтвердила отсутствие пользователя (удалён)
                        session.clear()
                        return redirect(url_for('auth.login'))
                    # БД недоступна — пропускаем проверку, не трогая сессию
                    pass
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
                _body = ''
                try:
                    _body = (resp.text or '')[:200]
                except Exception:
                    pass
                flash(f'Сервис недоступен [admin: ok={resp.ok} status={resp.status_code} cb={getattr(resp, "circuit_open", "?")} body={_body}]', 'danger')
                return redirect(url_for('jobs.index'))
            except Exception as e:
                # X8: fail-closed — при ошибке БД блокируем доступ
                import logging
                _logger = logging.getLogger(__name__)
                _logger.warning('admin_required DB error: %s', e, exc_info=True)
                flash(f'Сервис недоступен [admin exception: {repr(e)[:200]}]', 'danger')
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





