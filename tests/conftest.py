"""Фикстуры и моки pytest для всего тестового набора.

Ключевой принцип: все внешние зависимости (Supabase, PostgREST, Redis)
мокаются ДО импорта приложения, чтобы избежать ConnectionError.
"""

import os
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests

# ═══════════════════════════════════════════════════════════════
# Константы для интеграционных тестов (HTTP-запросы к реальному серверу)
# ═══════════════════════════════════════════════════════════════

BASE_URL = os.environ.get('TEST_BASE_URL', 'http://localhost:8000')
EMPLOYER_EMAIL = os.environ.get('TRUDNIK_EMPLOYER_EMAIL', 'employer@test.local')
EMPLOYER_PASSWORD = os.environ.get('TRUDNIK_EMPLOYER_PASS', 'test')
WORKER_EMAIL = os.environ.get('TRUDNIK_WORKER_EMAIL', 'worker@test.local')
WORKER_PASSWORD = os.environ.get('TRUDNIK_WORKER_PASS', 'test')
ADMIN_EMAIL = os.environ.get('TRUDNIK_ADMIN_EMAIL', 'admin@test.local')
ADMIN_PASSWORD = os.environ.get('TRUDNIK_ADMIN_PASS', 'test')


# ═══════════════════════════════════════════════════════════════
# Хелперы для интеграционных тестов (сессии, CSRF, логин)
# ═══════════════════════════════════════════════════════════════

def _extract_job_id_from_redirect(text_or_url, resp=None) -> str | None:
    """Извлекает job_id из URL редиректа или HTML.

    Совместимые формы: (str) | (session, response) — во второй берётся
    response.url и response.text.
    """
    if resp is not None:
        for source in (getattr(resp, 'url', ''), getattr(resp, 'text', '')):
            match = re.search(r'/jobs/([a-f0-9\-]+)', source)
            if match:
                return match.group(1)
        return None
    match = re.search(r'/jobs/([a-f0-9\-]+)', text_or_url)
    if match:
        return match.group(1)
    return None


def extract_csrf_token(html: str) -> str | None:
    """Извлекает CSRF-токен из HTML-страницы.

    Порядок: скрытое поле формы `_csrf_token`/`csrf_token` (значение value=),
    затем meta-тег csrf-token. Точные паттерны — НЕ «жадный» fallback
    (старый fallback захватывал value атрибута type="hidden").
    """
    for pat in (r'name="_csrf_token"[^>]*value="([^"]+)"',
                r'name="csrf_token"[^>]*value="([^"]+)"',
                r'value="([^"]+)"[^>]*name="_csrf_token"',
                r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"'):
        match = re.search(pat, html)
        if match:
            return match.group(1)
    return None


def get_csrf_from_page(session: requests.Session, url: str) -> str | None:
    """Загружает страницу и возвращает CSRF-токен из HTML."""
    resp = session.get(url, timeout=30)
    if resp.status_code == 200:
        return extract_csrf_token(resp.text)
    return None


def _get_live_csrf(session) -> str:
    """Реальный CSRF-токен для live-сессии (кэшируется на объекте Session).

    Middleware сверяет session['_csrf_token']; в mock-режиме (TESTING) CSRF
    отключён и токен не используется, но live integration-тесты требуют
    валидного значения.
    """
    cached = getattr(session, '_trudnik_csrf', None)
    if cached:
        return cached
    try:
        resp = session.get(f'{BASE_URL}/profile', timeout=30)
        token = extract_csrf_token(resp.text)
        if token:
            try:
                session._trudnik_csrf = token
            except Exception:
                pass
            return token
    except Exception:
        pass
    return 'test-csrf-token'


def csrf_headers(token=None):
    """Заголовки с CSRF для JSON-запросов.

    Принимает токен (строка), requests.Session (live: токен достанется со
    страницы) или None (mock-режим: заглушка). Имя заголовка — строго
    `X-CSRF-Token` (middleware.py:csrf_check).
    """
    import requests as _rq
    if isinstance(token, _rq.Session):
        token = _get_live_csrf(token)
    if token is None:
        token = 'test-csrf-token'
    return {'X-CSRF-Token': str(token), 'Content-Type': 'application/json'}


def form_with_csrf(data_dict=None, csrf=None, **kwargs):
    """Форма с CSRF-токеном. Совместимые формы вызова:

    - form_with_csrf(session, **fields)        — live: реальный токен со страницы
    - form_with_csrf(session, csrf, **fields)  — live: токен передан явно
    - form_with_csrf(dict, csrf)               — dict + явный токен
    - form_with_csrf(**fields) / form_with_csrf(dict, **fields) — mock: заглушка
    """
    import requests as _rq
    if isinstance(data_dict, _rq.Session):
        kwargs['_csrf_token'] = csrf or _get_live_csrf(data_dict)
        return dict(kwargs)
    data_dict = dict(data_dict or {})
    data_dict.update(kwargs)
    data_dict['_csrf_token'] = csrf or 'test-csrf-token'
    return data_dict


def _resp_read(f):
    """Читает один RESP-ответ из файла сокета."""
    line = f.readline()
    if not line:
        raise ConnectionError('redis closed connection')
    kind, payload = line[:1], line[1:-2]
    if kind == b'+':
        return payload.decode()
    if kind == b'-':
        raise RuntimeError('redis error: ' + payload.decode(errors='replace'))
    if kind == b':':
        return int(payload)
    if kind == b'$':
        n = int(payload)
        if n == -1:
            return None
        return f.read(n + 2)[:-2]
    if kind == b'*':
        n = int(payload)
        if n == -1:
            return None
        return [_resp_read(f) for _ in range(n)]
    raise RuntimeError(f'unknown RESP type: {kind!r}')


def _resp_command(f, *args):
    """Минимальный RESP-клиент: отправка команды + чтение ответа."""
    cmd = b'*' + str(len(args)).encode() + b'\r\n'
    for a in args:
        b = a.encode() if isinstance(a, str) else a
        cmd += b'$' + str(len(b)).encode() + b'\r\n' + b + b'\r\n'
    f.write(cmd)
    f.flush()
    return _resp_read(f)


def _clear_login_rate_limits():
    """Сбрасывает Redis-ключи rate-limit/lockout перед тестовым логином.

    Чистим: (1) ratelimit:/login:* декоратора; (2) C22 per-account
    login_attempts/login_lockout; (3) per-IP login_ip:*. Тестовая
    инфраструктура против локального docker-Redis — прод не затрагивается.

    ВАЖНО: raw-socket RESP вместо `import redis` — conftest подменяет
    sys.modules['redis'] моком (строка выше), реальный клиент из импорта
    недоступен.
    """
    import os
    import socket
    from urllib.parse import urlparse
    try:
        url = os.environ.get(
            'REDIS_URL', 'redis://:trudnik-local-dev@localhost:6379/0')
        u = urlparse(url)
        sock = socket.create_connection((u.hostname or 'localhost',
                                         u.port or 6379), timeout=2)
        f = sock.makefile('rbw')
        try:
            password = (u.password or '').strip(':')
            if password:
                _resp_command(f, 'AUTH', password)
            db = u.path.lstrip('/') or '0'
            if db != '0':
                _resp_command(f, 'SELECT', db)
            for pattern in (b'ratelimit:/login:*', b'ratelimit:/register:*',
                            b'login_attempts:*', b'login_lockout:*',
                            b'login_ip:*'):
                keys = _resp_command(f, 'KEYS', pattern) or []
                if keys:
                    _resp_command(f, 'DEL', *keys)
        finally:
            sock.close()
    except Exception:
        pass  # Redis недоступен — лимиты и так не работают (fail-open)


def login_as(session: requests.Session, email: str, password: str,
             role: str = 'worker') -> bool:
    """Логинит пользователя и возвращает True при успехе.

    Строгая проверка: 200 от followed-redirect — не гарантия авторизации
    (форма логина с flash тоже отдаёт 200). Успех = целевая страница НЕ
    содержит формы логина / flash «Неверный email или пароль».
    """
    _clear_login_rate_limits()
    resp = session.get(f'{BASE_URL}/login', timeout=30)
    csrf = extract_csrf_token(resp.text)
    if not csrf:
        return False
    resp = session.post(
        f'{BASE_URL}/login',
        data={'email': email, 'password': password, 'csrf_token': csrf},
        timeout=30,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        return False
    if 'name="password"' in resp.text and 'Неверный email или пароль' in resp.text:
        return False
    # авторизованный редирект ведёт на /, /my-jobs — не на /login
    return not resp.url.rstrip('/').endswith('/login')


def relogin_if_expired(session: requests.Session, email: str, password: str) -> None:
    """Перелогинивает сессию, если токен истёк."""
    # Простая проверка: пробуем GET /profile, если 302 — логинимся
    resp = session.get(f'{BASE_URL}/profile', timeout=30, allow_redirects=False)
    if resp.status_code in (302, 401):
        login_as(session, email, password)


# ═══════════════════════════════════════════════════════════════
# Шаг 1: Мокаем PostgREST ДО импорта app
# ═══════════════════════════════════════════════════════════════

# Включаем in-memory mock режим (проверяется в app/testing/mock_postgrest.py)
os.environ['POSTGREST_MOCK_MODE'] = '1'
# Пароль для тестового входа (используется mock-авторизацией)
os.environ['TEST_USER_PASSWORD'] = 'test'



# Мокаем redis — ВСЕГДА, даже если пакет установлен.
# Без этого @patch('redis.from_url') не работает (redis — C-расширение,
# которое unittest.mock не может пропатчить на уровне атрибутов).
# Хранилище для stateful redis-мока: Flask-Session (SESSION_TYPE='redis')
# сохраняет/читает сессии через get/set/setex/delete/exists. Без реального
# хранилища session_transaction() не roundtrip'ится → тесты с auth-сессией
# получают 302 (redirect to login) вместо ожидаемых 403/429/200.
_mock_redis_store: dict = {}


def _mock_set(name, val, *a, **k):
    _mock_redis_store[name] = val
    return True


def _mock_setex(name, ttl, val, *a, **k):
    _mock_redis_store[name] = val
    return True


def _mock_delete(*names):
    return sum(1 for n in names if _mock_redis_store.pop(n, None) is not None)


def _mock_exists(*names):
    return sum(1 for n in names if n in _mock_redis_store)


_mock_redis_client = MagicMock()
_mock_redis_client.ping.return_value = True
_mock_redis_client.publish.return_value = 1
_mock_redis_client.close.return_value = None
_mock_redis_client.get.side_effect = lambda name: _mock_redis_store.get(name)
_mock_redis_client.set.side_effect = _mock_set
_mock_redis_client.setex.side_effect = _mock_setex
_mock_redis_client.delete.side_effect = _mock_delete
_mock_redis_client.exists.side_effect = _mock_exists

_mock_redis_module = MagicMock()
_mock_redis_module.from_url.return_value = _mock_redis_client
_mock_redis_module.Redis.return_value = _mock_redis_client
_mock_redis_module.ConnectionError = Exception  # Чтобы except redis.ConnectionError не падал

# Делаем redis-мок полноценным «пакетом» (атрибут __path__) и регистрируем
# подмодуль redis.asyncio, чтобы `import redis.asyncio as aioredis`
# (используется в websocket_server/main.py) корректно разрешался в тестах,
# а не падал с "'redis' is not a package".
_mock_async_redis_client = MagicMock()
_mock_async_redis_client.ping = AsyncMock(return_value=True)
_mock_async_redis_client.close = AsyncMock()
_mock_async_redis_module = MagicMock()
_mock_async_redis_module.from_url.return_value = _mock_async_redis_client
_mock_async_redis_module.Redis.return_value = _mock_async_redis_client
_mock_async_redis_module.ConnectionError = Exception

_mock_redis_module.__path__ = []  # признак пакета для import machinery
_mock_redis_module.asyncio = _mock_async_redis_module

sys.modules['redis'] = _mock_redis_module
sys.modules['redis.asyncio'] = _mock_async_redis_module

# Мокаем python-magic на случай, если пакет не установлен
_mock_magic = MagicMock()
_mock_magic.from_buffer.return_value = 'image/jpeg'
sys.modules['magic'] = _mock_magic

# ═══════════════════════════════════════════════════════════════
# Шаг 2: Фикстуры pytest
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def mock_postgrest_client(monkeypatch):
    """Автоматически мокает PostgREST-клиент для всех тестов.

    Подменяет функции в app.utils.postgrest_client (postgrest_request,
    postgrest_admin_request, postgrest_rpc) на заглушки, возвращающие
    пустые/успешные ответы. Это предотвращает любые реальные HTTP-запросы
    к PostgREST. (Модуль app.utils.supabase удалён при миграции на PostgREST.)
    """
    from app.utils import PostgrestResponse

    def mock_ok_response(*args, **kwargs):
        return PostgrestResponse(ok=True, status_code=200, data=[], text='[]')

    def mock_json_response(data=None):
        if data is None:
            data = []
        return PostgrestResponse(ok=True, status_code=200, data=data, text=str(data))

    # Мокаем основные функции запросов к PostgREST
    def _smart_postgrest_request(method=None, url=None, **kwargs):
        """Умный мок: возвращает профиль для B5/role_required проверок."""
        # B5: проверка существования пользователя и role_required
        if isinstance(url, str) and 'profiles?id=eq.' in url and 'select=id' in url:
            return PostgrestResponse(ok=True, status_code=200,
                                     data=[{'id': 'mock'}], text='[{"id":"mock"}]')
        # role_required / admin_required запрашивают роль — возвращаем роль
        # из текущей сессии (тесты выставляют session['role'] в фикстурах),
        # чтобы admin/worker/employer-маршруты корректно проходили проверку роли.
        if isinstance(url, str) and 'profiles?id=eq.' in url and 'select=role' in url:
            try:
                from flask import session as _flask_session
                _role = _flask_session.get('role', 'employer')
            except Exception:
                _role = 'employer'
            return PostgrestResponse(ok=True, status_code=200,
                                     data=[{'role': _role}], text=str([{'role': _role}]))
        # B10: проверка password_changed_at
        if isinstance(url, str) and 'profiles?id=eq.' in url and 'password_changed_at' in url:
            return PostgrestResponse(ok=True, status_code=200,
                                     data=[{'password_changed_at': None}], text='[{"password_changed_at":null}]')
        return PostgrestResponse(ok=True, status_code=200, data=[], text='[]')

    monkeypatch.setattr(
        'app.utils.postgrest_request',
        _smart_postgrest_request
    )
    monkeypatch.setattr(
        'app.utils.postgrest_admin_request',
        _smart_postgrest_request
    )
    monkeypatch.setattr(
        'app.utils.postgrest_rpc',
        lambda *a, **kw: PostgrestResponse(ok=True, status_code=200, data={'success': True}, text='{"success": true}')
    )

    # Также патчим ИСТОЧНИК — postgrest_client.* (модуль), т.к. blueprints/decorators
    # делают `from app.utils import postgrest_request` (и admin_request), что захватывает
    # ссылку из app.utils.__init__, указывающую на postgrest_client.* . Без этого
    # admin_required/role_required дёргают «настоящую» admin_request → реальная сеть.
    import app.utils.postgrest_client as _pgc
    monkeypatch.setattr(_pgc, 'postgrest_request', _smart_postgrest_request)
    monkeypatch.setattr(_pgc, 'postgrest_admin_request', _smart_postgrest_request)

    # Мокаем Celery-задачи, чтобы избежать попыток подключения к Redis
    try:
        from app.tasks.email_tasks import send_email_notification
        send_email_notification.delay = lambda *a, **kw: None
        send_email_notification.apply_async = lambda *a, **kw: None
    except Exception:
        pass

    try:
        from app.tasks.push_tasks import send_push_notification
        send_push_notification.delay = lambda *a, **kw: None
        send_push_notification.apply_async = lambda *a, **kw: None
    except Exception:
        pass

    # Мокаем redis внутри redis_publisher через monkeypatch
    # (monkeypatch работает на уровне атрибутов, надёжнее чем sys.modules)
    try:
        import app.services.redis_publisher as rp_mod

        _mock_client = MagicMock()
        _mock_client.ping.return_value = True
        _mock_client.publish.return_value = 1
        _mock_client.close.return_value = None

        _mock_redis = MagicMock()
        _mock_redis.from_url.return_value = _mock_client
        _mock_redis.Redis.return_value = _mock_client
        _mock_redis.ConnectionError = Exception

        monkeypatch.setattr(rp_mod, 'redis', _mock_redis, raising=False)
        monkeypatch.setattr(rp_mod, '_REDIS_AVAILABLE', True, raising=False)
    except Exception:
        pass

    return


@pytest.fixture
def app_client(mock_postgrest_client):
    """Создаёт тестовый Flask-клиент с включённым режимом TESTING.

    В режиме TESTING:
    - CSRF-защита отключена
    - База данных in-memory (мок)
    - Не требуются реальные внешние сервисы
    """
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['SERVER_NAME'] = 'localhost'
    # Отключаем перехват исключений в тестах для читаемых traceback'ов
    app.config['PROPAGATE_EXCEPTIONS'] = True
    # В тестах — client-side cookie-сессии вместо Redis-backed (SESSION_TYPE='redis'):
    # session_transaction() roundtrip'ится нативно, auth-сессии работают без живого Redis.
    from flask.sessions import SecureCookieSessionInterface
    app.session_interface = SecureCookieSessionInterface()
    return app.test_client()


@pytest.fixture
def app_context(mock_postgrest_client):
    """Создаёт контекст приложения Flask (без клиента)."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.app_context():
        yield app


# ═══════════════════════════════════════════════════════════════
# Фикстуры для интеграционных тестов (HTTP-запросы к реальному серверу)
# Эти фикстуры создают requests.Session и логинят пользователей.
# Требуют запущенного Flask-сервера на TEST_BASE_URL (по умолчанию localhost:8000).
#
# scope='module': сессия логинится ОДИН раз на модуль. Причинa — rate limit
# /login = 10 POST/60с на IP (app/utils/rate_limit_decorator.py, hardcoded):
# function-scope давал >100 логинов на модуль и suite ловил 429 уже на
# 11-м тесте. Тесты не вызывают logout, состояние сессии переиспользуется
# безопасно (каждый тест — независимая HTTP-операция от имени того же юзера).
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def employer_session():
    """Создаёт авторизованную сессию работодателя (requests.Session)."""
    session = requests.Session()
    ok = login_as(session, EMPLOYER_EMAIL, EMPLOYER_PASSWORD, role='employer')
    if not ok:
        pytest.skip(f'Не удалось залогинить работодателя на {BASE_URL}')
    return session


@pytest.fixture(scope='module')
def worker_session():
    """Создаёт авторизованную сессию трудника (requests.Session)."""
    session = requests.Session()
    ok = login_as(session, WORKER_EMAIL, WORKER_PASSWORD, role='worker')
    if not ok:
        pytest.skip(f'Не удалось залогинить трудника на {BASE_URL}')
    return session


@pytest.fixture(scope='module')
def admin_session():
    """Создаёт авторизованную сессию администратора (requests.Session)."""
    session = requests.Session()
    ok = login_as(session, ADMIN_EMAIL, ADMIN_PASSWORD, role='admin')
    if not ok:
        pytest.skip(f'Не удалось залогинить админа на {BASE_URL}')
    return session


@pytest.fixture
def published_job_id():
    """ID опубликованного задания для тестов."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def created_job_id(employer_session):
    """Создаёт тестовое задание и возвращает его ID."""
    csrf = get_csrf_from_page(employer_session, f'{BASE_URL}/jobs/new')
    if not csrf:
        pytest.skip('Не удалось получить CSRF-токен для создания задания')
    resp = employer_session.post(
        f'{BASE_URL}/jobs/new',
        data=form_with_csrf({
            'title': 'Test Job for Integration Tests',
            'description': 'Auto-created by pytest fixture',
            'location': 'Москва',
            'category': 'Разнорабочие',
            'payment': '1000',
            'max_workers': '5',
        }, csrf),
        timeout=30,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        pytest.skip(f'Не удалось создать тестовое задание: {resp.status_code}')
    # Extract job_id from URL or response
    match = re.search(r'/jobs/([a-f0-9\-]+)', resp.text)
    if match:
        return match.group(1)
    match = re.search(r'/jobs/([a-f0-9\-]+)', resp.url)
    if match:
        return match.group(1)
    pytest.skip('Не удалось извлечь ID созданного задания')
    return None


@pytest.fixture
def accepted_application_id(employer_session, worker_session, created_job_id):
    """Создаёт accepted-отклик и возвращает (application_id, job_id)."""
    # Worker applies
    csrf = get_csrf_from_page(worker_session, f'{BASE_URL}/jobs/{created_job_id}')
    if not csrf:
        pytest.skip('Не удалось получить CSRF для отклика')
    resp = worker_session.post(
        f'{BASE_URL}/jobs/{created_job_id}/apply',
        data=form_with_csrf({}, csrf),
        timeout=30,
        allow_redirects=True,
    )
    if resp.status_code != 200:
        pytest.skip(f'Не удалось откликнуться: {resp.status_code}')
    # Employer accepts - find application_id
    resp2 = employer_session.get(f'{BASE_URL}/my-applications', timeout=30)
    match = re.search(r'data-app-id="([^"]+)"', resp2.text)
    if not match:
        match = re.search(r'/applications/([a-f0-9\-]+)/accept', resp2.text)
    if not match:
        pytest.skip('Не удалось найти ID отклика')
    app_id = match.group(1)
    csrf2 = get_csrf_from_page(employer_session, f'{BASE_URL}/my-applications')
    if csrf2:
        employer_session.post(
            f'{BASE_URL}/applications/{app_id}/accept',
            data=form_with_csrf({}, csrf2),
            timeout=30,
        )
    return (app_id, created_job_id)


def pytest_sessionfinish(session, exitstatus):
    """Очистка env vars после тестов."""
    import os
    os.environ.pop('POSTGREST_MOCK_MODE', None)
    os.environ.pop('TEST_PASSWORD', None)


# ═══════════════════════════════════════════════════════════════
# Auto-skip integration tests when the live app / browser is absent.
# Integration-тесты (live HTTP к app:8000, Selenium, Playwright e2e) требуют
# поднятый стек (app + PostgREST + Redis + DB) и/или браузер. Без него они
# авто-skip'аются, чтобы `pytest tests` оставался зелёным для unit/mock-набора.
# Запустить integration: поднять docker-compose ИЛИ AMVERA_RUN_INTEGRATION=1.
# ═══════════════════════════════════════════════════════════════
_INTEGRATION_MARKERS = (
    'BASE_URL', 'TEST_BASE_URL',
    'localhost:8000', 'localhost:5000', '127.0.0.1:8000', '127.0.0.1:5000',
    'webdriver', 'from selenium', 'async_playwright', 'chromium',
    'requests.get(f', 'requests.post(f', 'requests.request(f',
)
_int_file_cache: dict = {}


def _is_integration_module(path: str) -> bool:
    if path in _int_file_cache:
        return _int_file_cache[path]
    try:
        with open(path, encoding='utf-8') as fh:
            src = fh.read()
    except OSError:
        _int_file_cache[path] = False
        return False
    result = any(m in src for m in _INTEGRATION_MARKERS)
    _int_file_cache[path] = result
    return result


def pytest_collection_modifyitems(config, items):
    import os as _os
    import socket as _socket
    from urllib.parse import urlparse

    if _os.environ.get('AMVERA_RUN_INTEGRATION', '').lower() in ('1', 'true', 'yes'):
        return  # integration принудительно разрешён

    base = _os.environ.get('TEST_BASE_URL', BASE_URL)
    try:
        u = urlparse(base)
        host = u.hostname or 'localhost'
        port = u.port or (443 if u.scheme == 'https' else 80)
        with _socket.create_connection((host, port), timeout=1):
            return  # app достижим — гоняем integration-тесты как обычно
    except OSError:
        pass

    skipped = 0
    for item in items:
        mod_file = getattr(getattr(item, 'module', None), '__file__', None)
        if mod_file and _is_integration_module(mod_file):
            item.add_marker(pytest.mark.skip(
                reason=f'integration: live app/browser not reachable at {base} '
                       f'(start stack or set AMVERA_RUN_INTEGRATION=1)'))
            skipped += 1
    if skipped:
        print(f'\n[conftest] auto-skipped {skipped} integration test(s): '
              f'app not reachable at {base}')
