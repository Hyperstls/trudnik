"""Стартовая инициализация: ожидание PostgREST, сброс Circuit Breaker."""

import logging
import os
import time

logger = logging.getLogger(__name__)


def wait_for_postgrest(app, max_wait: int = 30, interval: int = 2) -> bool:
    """Ожидание готовности PostgREST при старте приложения.

    Предотвращает открытие Circuit Breaker из-за race condition
    при запуске docker-compose стека (Flask может стартовать раньше PostgREST).

    Args:
        app: экземпляр Flask.
        max_wait: максимальное время ожидания в секундах.
        interval: интервал между попытками в секундах.

    Returns:
        True если PostgREST ответил, иначе False.
    """
    import requests as _req
    postgrest_url = os.environ.get('POSTGREST_URL', 'http://postgrest:3000').strip()
    deadline = time.time() + max_wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            r = _req.get(f'{postgrest_url}/skills?select=id&limit=1', timeout=5)
            if r.status_code in (200, 401):
                # 200 = OK, 401 = RLS (ожидаемо без JWT) — PostgREST жив
                app.logger.info(
                    'PostgREST ready after %d attempt(s) (status=%d)',
                    attempt, r.status_code
                )
                # Сбрасываем Circuit Breaker'ы после успешного коннекта
                try:
                    from app.utils.postgrest_client import _cb_postgrest, _cb_admin
                    _cb_postgrest.reset()
                    _cb_admin.reset()
                except Exception:
                    pass
                return True
            app.logger.warning(
                'PostgREST attempt %d: unexpected status %d',
                attempt, r.status_code
            )
        except Exception as e:
            app.logger.warning(
                'PostgREST attempt %d: %s', attempt, e
            )
        time.sleep(interval)
    app.logger.error('PostgREST not available after %d attempts', attempt)
    return False
