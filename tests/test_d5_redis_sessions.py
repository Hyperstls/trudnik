"""D5: Server-side Redis-сессии (Flask-Session) — регрессионные тесты.

Контракт:
- В обычном режиме create_app() инициализирует RedisSessionInterface (сессии в Redis).
- В mock/test-режиме (POSTGREST_MOCK_MODE=1) Session(app) НЕ вызывается —
  остаются дефолтные cookie-сессии Flask, чтобы unit-тесты не зависели от Redis.

Эти тесты проверяют второй (mock) путь, т.к. conftest глобально мокает модуль redis.
"""

import os

from flask.sessions import SecureCookieSessionInterface


def test_mock_mode_keeps_cookie_sessions(app_context):
    """В mock-режиме session_interface остаётся дефолтным SecureCookieSessionInterface."""
    # POSTGREST_MOCK_MODE=1 выставлен в conftest ДО импорта приложения.
    assert os.environ.get('POSTGREST_MOCK_MODE', '').lower() in ('1', 'true', 'yes')
    from app import create_app
    app = create_app()
    # SESSION_REDIS не должен устанавливаться (инициализация пропущена)
    assert 'SESSION_REDIS' not in app.config
    assert isinstance(app.session_interface, SecureCookieSessionInterface)


def test_session_config_present(app_context):
    """Конфиг D5 на месте: тип redis, префикс, signer, TTL."""
    from app import create_app
    app = create_app()
    assert app.config['SESSION_TYPE'] == 'redis'
    assert app.config['SESSION_KEY_PREFIX'] == 'session:'
    assert app.config['SESSION_USE_SIGNER'] is True
    assert app.config['SESSION_REDIS_URL']  # задан (из REDIS_URL)
