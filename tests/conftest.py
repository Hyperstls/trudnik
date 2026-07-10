"""Фикстуры и моки pytest для всего тестового набора.

Ключевой принцип: все внешние зависимости (Supabase, PostgREST, Redis)
мокаются ДО импорта приложения, чтобы избежать ConnectionError.
"""

import os
import re
import sys
from unittest.mock import MagicMock, patch

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

def _extract_job_id_from_redirect(text_or_url: str) -> str | None:
    """Извлекает job_id из URL редиректа или HTML."""
    match = re.search(r'/jobs/([a-f0-9\-]+)', text_or_url)
    if match:
        return match.group(1)
    return None


def extract_csrf_token(html: str) -> str | None:
    """Извлекает CSRF-токен из HTML-страницы."""
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if match:
        return match.group(1)
    match = re.search(r'csrf_token[^=]*=[^"]*"([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def get_csrf_from_page(session: requests.Session, url: str) -> str | None:
    """Загружает страницу и возвращает CSRF-токен из HTML."""
    resp = session.get(url, timeout=30)
    if resp.status_code == 200:
        return extract_csrf_token(resp.text)
    return None


def csrf_headers(token=None):
    """Возвращает заголовки с CSRF-токеном для JSON-запросов."""
    if token is None:
        token = 'test-csrf-token'
    return {'X-CSRFToken': str(token), 'Content-Type': 'application/json'}


def form_with_csrf(data_dict=None, **kwargs):
    """Принимает и dict, и keyword arguments."""
    if data_dict is None:
        data_dict = {}
    data_dict.update(kwargs)
    # Добавляем CSRF токен
    data_dict['_csrf_token'] = 'test-csrf-token'
    return data_dict


def login_as(session: requests.Session, email: str, password: str,
             role: str = 'worker') -> bool:
    """Логинит пользователя и возвращает True при успехе."""
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
    return resp.status_code == 200


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
_mock_redis_client = MagicMock()
_mock_redis_client.ping.return_value = True
_mock_redis_client.publish.return_value = 1
_mock_redis_client.close.return_value = None

_mock_redis_module = MagicMock()
_mock_redis_module.from_url.return_value = _mock_redis_client
_mock_redis_module.Redis.return_value = _mock_redis_client
_mock_redis_module.ConnectionError = Exception  # Чтобы except redis.ConnectionError не падал

sys.modules['redis'] = _mock_redis_module

# Мокаем python-magic на случай, если пакет не установлен
_mock_magic = MagicMock()
_mock_magic.from_buffer.return_value = 'image/jpeg'
sys.modules['magic'] = _mock_magic

# ═══════════════════════════════════════════════════════════════
# Шаг 2: Фикстуры pytest
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def mock_postgrest_client(monkeypatch):
    """Автоматически мокает Supabase/PostgREST клиент для всех тестов.

    Подменяет функции в app.utils.supabase на заглушки, возвращающие
    пустые/успешные ответы. Это предотвращает любые реальные HTTP-запросы.
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
        # role_required запрашивает роль
        if isinstance(url, str) and 'profiles?id=eq.' in url and 'select=role' in url:
            return PostgrestResponse(ok=True, status_code=200,
                                     data=[{'role': 'employer'}], text='[{"role":"employer"}]')
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
        lambda *a, **kw: PostgrestResponse(ok=True, status_code=200, data=[], text='[]')
    )
    monkeypatch.setattr(
        'app.utils.postgrest_rpc',
        lambda *a, **kw: PostgrestResponse(ok=True, status_code=200, data={'success': True}, text='{"success": true}')
    )

    # Также патчим ИСТОЧНИК — postgrest_client.postgrest_request
    # Это нужно потому что decorators.py делает: from app.utils import postgrest_request as _pgreq
    # что захватывает ссылку из app.utils.__init__, которая указывает на postgrest_client.postgrest_request
    import app.utils.postgrest_client as _pgc
    monkeypatch.setattr(_pgc, 'postgrest_request', _smart_postgrest_request)

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
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SERVER_NAME'] = 'localhost'
    # Отключаем перехват исключений в тестах для читаемых traceback'ов
    app.config['PROPAGATE_EXCEPTIONS'] = True
    return app.test_client()


@pytest.fixture
def app_context(mock_postgrest_client):
    """Создаёт контекст приложения Flask (без клиента)."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        yield app


# ═══════════════════════════════════════════════════════════════
# Фикстуры для интеграционных тестов (HTTP-запросы к реальному серверу)
# Эти фикстуры создают requests.Session и логинят пользователей.
# Требуют запущенного Flask-сервера на TEST_BASE_URL (по умолчанию localhost:8000).
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def employer_session():
    """Создаёт авторизованную сессию работодателя (requests.Session)."""
    session = requests.Session()
    ok = login_as(session, EMPLOYER_EMAIL, EMPLOYER_PASSWORD, role='employer')
    if not ok:
        pytest.skip(f'Не удалось залогинить работодателя на {BASE_URL}')
    return session


@pytest.fixture
def worker_session():
    """Создаёт авторизованную сессию трудника (requests.Session)."""
    session = requests.Session()
    ok = login_as(session, WORKER_EMAIL, WORKER_PASSWORD, role='worker')
    if not ok:
        pytest.skip(f'Не удалось залогинить трудника на {BASE_URL}')
    return session


@pytest.fixture
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
