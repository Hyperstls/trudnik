"""Rate Limiting — in-memory ре-экспорт для обратной совместимости.

Предпочитать импорт из app.decorators (Redis-based) для нового кода.
"""

import time
from collections import defaultdict
from functools import wraps
from typing import Any, Callable, Dict, List, TypeVar

from flask import current_app, flash, jsonify, redirect, request, url_for

F = TypeVar('F', bound=Callable[..., Any])

_rate_limits: Dict[str, List[float]] = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX_REQUESTS = 10


def rate_limit(f: F) -> F:
    """Декоратор: ограничение частоты POST-запросов по IP (in-memory).

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
        ip = request.remote_addr or '127.0.0.1'
        now = time.time()
        _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < _RATE_WINDOW]
        if len(_rate_limits[ip]) >= _RATE_MAX_REQUESTS:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
               'application/json' in request.headers.get('Accept', ''):
                return jsonify({'error': 'Слишком много попыток. Подождите минуту.'}), 429
            flash('Слишком много попыток. Подождите минуту.', 'danger')
            return redirect(url_for('auth.login'))
        _rate_limits[ip].append(now)
        return f(*args, **kwargs)
    return decorated  # type: ignore[return-value]
