"""Rate limit decorator — Redis-based rate limiting для gunicorn worker'ов.

Этот модуль НЕ импортирует ничего из app.utils или app.decorators,
чтобы избежать циклических импортов.
"""

from functools import wraps
import logging

from flask import current_app, flash, jsonify, redirect, request, session, url_for

logger = logging.getLogger(__name__)

_RATE_WINDOW = 60  # секунд
_RATE_MAX_REQUESTS = 10  # запросов в окне


def rate_limit(f=None, fail_open: bool = True):
    """Декоратор: ограничение частоты POST-запросов через Redis.

    Использует Redis INCR + EXPIRE вместо in-memory словаря,
    что корректно работает с несколькими gunicorn worker'ами.

    Ключ: ratelimit:{endpoint}:{user_id}

    Args:
        f: функция-обработчик маршрута.
        fail_open: если True — при ошибке Redis пропускать запрос (graceful degradation).
                   если False — отклонять запрос (fail-closed, для /login, /register).

    Returns:
        Декорированная функция с rate limiting (10 попыток в минуту).
    """
    if f is None:
        return lambda func: rate_limit(func, fail_open=fail_open)

    @wraps(f)
    def decorated(*args, **kwargs):
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
                if fail_open:
                    # Redis недоступен — разрешаем запрос (graceful degradation)
                    return f(*args, **kwargs)
                else:
                    # fail-closed: Redis недоступен — отклоняем запрос
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                       'application/json' in request.headers.get('Accept', ''):
                        return jsonify({'error': 'Сервис временно недоступен. Попробуйте позже.'}), 503
                    flash('Сервис временно недоступен. Попробуйте позже.', 'danger')
                    return redirect(url_for('auth.login'))

            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, _RATE_WINDOW)

            if current > _RATE_MAX_REQUESTS:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                   'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': 'Слишком много попыток. Подождите минуту.'}), 429
                flash('Слишком много попыток. Подождите минуту.', 'danger')
                return redirect(url_for('auth.login'))
        except Exception as e:
            logger.warning('rate_limit Redis error: %s', e, exc_info=True)
            if fail_open:
                # Ошибка Redis — разрешаем запрос (graceful degradation)
                pass
            else:
                # fail-closed: ошибка Redis — отклоняем запрос
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
                   'application/json' in request.headers.get('Accept', ''):
                    return jsonify({'error': 'Сервис временно недоступен. Попробуйте позже.'}), 503
                flash('Сервис временно недоступен. Попробуйте позже.', 'danger')
                return redirect(url_for('auth.login'))

        return f(*args, **kwargs)

    return decorated
