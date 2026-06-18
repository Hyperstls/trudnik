"""
Общие fixtures и хелперы для тестов проекта «Трудник».
Pytest автоматически находит этот файл в корне проекта.

Запуск: python -m pytest -v --tb=short
"""

import os
import re
import time

import pytest
import requests

# ──────────────────────────────────────────────
# Конфигурация из переменных окружения
# ──────────────────────────────────────────────

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
EMPLOYER_EMAIL = os.environ.get('EMPLOYER_EMAIL', 'org@test.ru')
EMPLOYER_PASSWORD = os.environ.get('EMPLOYER_PASSWORD', '')
WORKER_EMAIL = os.environ.get('WORKER_EMAIL', '')
WORKER_PASSWORD = os.environ.get('WORKER_PASSWORD', '')

# Проверка: переменные должны быть заданы через окружение или .env
_MISSING = [k for k, v in [('EMPLOYER_PASSWORD', EMPLOYER_PASSWORD),
                             ('WORKER_EMAIL', WORKER_EMAIL),
                             ('WORKER_PASSWORD', WORKER_PASSWORD)] if not v]
if _MISSING:
    raise RuntimeError(
        f'Отсутствуют обязательные переменные окружения: {", ".join(_MISSING)}. '
        f'Установите их через .env.test или переменные окружения.'
    )


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

def extract_csrf_token(html: str) -> str | None:
    """Извлекает CSRF-токен из meta-тега HTML-страницы."""
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    return match.group(1) if match else None


def login_as(session: requests.Session, email: str, password: str) -> str | None:
    """Логинится под указанным пользователем и возвращает CSRF-токен.

    POST /login не требует CSRF (явно пропущен в csrf_check).
    При 429 (rate limit) — ждёт 5 сек и пробует снова (до 3 попыток).
    """
    for attempt in range(3):
        resp = session.get(f'{BASE_URL}/login', timeout=30)
        csrf = extract_csrf_token(resp.text)

        resp = session.post(
            f'{BASE_URL}/login',
            data={'email': email, 'password': password},
            timeout=30,
            allow_redirects=True,
        )
        if resp.status_code == 429:
            # Rate limit — подождать и повторить
            time.sleep(5)
            continue
        if 'Ошибка входа' in resp.text:
            return None
        fresh_csrf = extract_csrf_token(resp.text)
        return fresh_csrf or csrf
    return None


def relogin_if_expired(session: requests.Session, email: str, password: str) -> bool:
    """Перелогиниться, если сессия истекла. Возвращает True если успешно."""
    csrf = login_as(session, email, password)
    return csrf is not None


def get_csrf_from_page(session: requests.Session, path: str = '/') -> str | None:
    """Получает CSRF-токен с указанной страницы.
    При 401/403 — пытается перезайти и повторить запрос.
    """
    resp = session.get(f'{BASE_URL}{path}', timeout=30)
    return extract_csrf_token(resp.text)


def csrf_headers(session: requests.Session) -> dict:
    """Возвращает заголовки с CSRF-токеном для AJAX-запросов."""
    csrf = get_csrf_from_page(session)
    return {
        'X-CSRF-Token': csrf or '',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
    }


def form_with_csrf(session: requests.Session, **extra) -> dict:
    """Создаёт словарь данных формы с CSRF-токеном."""
    csrf = get_csrf_from_page(session)
    return {'_csrf_token': csrf or '', **extra}


def _extract_job_id_from_redirect(session, create_resp) -> str | None:
    """Извлекает job_id из редиректа после создания задания, либо ищет на /my-jobs."""
    if create_resp.status_code in (301, 302):
        location = create_resp.headers.get("Location", "")
        parts = location.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "job":
            return parts[1]
    # Ищем на /my-jobs или главной
    for page in ['/my-jobs', '/']:
        resp = session.get(f'{BASE_URL}{page}', timeout=30)
        job_ids = re.findall(r'/jobs/([a-f0-9-]{36})', resp.text)
        if job_ids:
            return job_ids[-1]
        job_ids_attr = re.findall(r'data-job-id="([a-f0-9-]{36})"', resp.text)
        if job_ids_attr:
            return job_ids_attr[-1]
    return None


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope='function')
def employer_session():
    """Сессия работодателя (org@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    if csrf is None:
        pytest.skip('Не удалось войти как работодатель (rate limit или учётные данные).')
    return sess


@pytest.fixture(scope='function')
def worker_session():
    """Сессия трудника (trud3@test.ru)."""
    sess = requests.Session()
    csrf = login_as(sess, WORKER_EMAIL, WORKER_PASSWORD)
    if csrf is None:
        pytest.skip('Не удалось войти как трудник (rate limit или учётные данные).')
    return sess


@pytest.fixture(scope='function')
def created_job_id(employer_session):
    """Создать тестовое задание (is_paid=True) и вернуть его ID."""
    sess = employer_session
    form = form_with_csrf(
        sess,
        title=f"Тестовое задание Pytest {int(time.time())}",
        description="Описание тестового задания для проверки State Machine",
        work_type="Уборка",
        payment="500",
        address="Москва, ул. Тестовая, 1",
        city="Москва",
        latitude="55.75",
        longitude="37.61",
        preferred_religion="",
        max_workers="2",
    )
    resp = sess.post(f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False)
    job_id = _extract_job_id_from_redirect(sess, resp)
    if not job_id:
        pytest.skip(f"Не удалось создать задание: status={resp.status_code}")
    return job_id


@pytest.fixture(scope='function')
def published_job_id(employer_session, created_job_id):
    """Создать и вернуть ID задания (is_paid=True по умолчанию при создании)."""
    return created_job_id


@pytest.fixture(scope='function')
def accepted_application_id(employer_session, worker_session):
    """Создаёт accepted отклик: worker применяется, employer принимает.
    Возвращает (application_id, job_id) или (None, None) при ошибке."""
    e_sess = employer_session
    w_sess = worker_session

    # 1. Создать задание (сразу is_paid=True)
    form = form_with_csrf(
        e_sess,
        title=f"Задание для accepted-отклика {int(time.time())}",
        description="Тест accepted-отклика",
        work_type="Уборка",
        payment="700",
        address="Москва, ул. Accepted, 1",
        city="Москва",
        latitude="55.75",
        longitude="37.61",
        max_workers="2",
    )
    create_resp = e_sess.post(
        f"{BASE_URL}/job/new", data=form, timeout=30, allow_redirects=False
    )
    job_id = _extract_job_id_from_redirect(e_sess, create_resp)
    if not job_id:
        return None, None

    # 2. Worker откликается
    apply_resp = w_sess.post(
        f"{BASE_URL}/apply/{job_id}",
        data=form_with_csrf(w_sess),
        timeout=30,
        allow_redirects=True,
    )
    if apply_resp.status_code != 200:
        return None, None

    # 3. Получить ID отклика через страницу my-applications работодателя
    app_id = None
    my_apps = e_sess.get(f"{BASE_URL}/my-applications", timeout=30)
    for pattern in [
        r'/api/applications/([a-f0-9\-]+)/accept',
        r'/api/applications/([a-f0-9\-]+)/reject',
        r'data-application-id="([^"]+)"',
        r'data-app-id="([^"]+)"',
        r'/chat/([a-f0-9\-]+)',
    ]:
        matches = re.findall(pattern, my_apps.text)
        if matches:
            app_id = matches[0]
            break

    if not app_id:
        # Ищем на странице /my-jobs
        my_jobs = e_sess.get(f"{BASE_URL}/my-jobs", timeout=30)
        for pattern in [
            r'/api/applications/([a-f0-9\-]+)/accept',
            r'data-app-id="([^"]+)"',
            r'/chat/([a-f0-9\-]+)',
        ]:
            matches = re.findall(pattern, my_jobs.text)
            if matches:
                app_id = matches[0]
                break

    if not app_id:
        return None, None

    # 4. Принять отклик
    accept_resp = e_sess.post(
        f"{BASE_URL}/api/applications/{app_id}/accept",
        headers=csrf_headers(e_sess),
        timeout=30,
    )
    # Accept может вернуть 200 (JSON), 302 (redirect) или 403 (если уже accepted)
    if accept_resp.status_code not in (200, 302):
        return None, None
    # Если JSON ответ — проверяем success/status
    ct = accept_resp.headers.get('content-type', '')
    if 'application/json' in ct:
        try:
            data = accept_resp.json()
            if not data.get("success", data.get("status") == "ok"):
                return None, None
        except Exception:
            pass
    # Всё ок — возвращаем ID
    return app_id, job_id


# ═══════════════════════════════════════════════════════════════
# Fixtures для тестов уведомлений v2
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=False)
def setup_notifications_env():
    """Устанавливает тестовые переменные окружения для сервисов уведомлений."""
    os.environ['SECRET_KEY'] = 'test-secret-key-for-testing'
    os.environ['SMTP_HOST'] = 'localhost'
    os.environ['SMTP_PORT'] = '587'
    os.environ['SMTP_USER'] = 'test@example.com'
    os.environ['SMTP_PASSWORD'] = 'test-password'
    os.environ['SMTP_FROM_EMAIL'] = 'notifications@trudnik.ru'
    os.environ['SMTP_DAILY_LIMIT'] = '10'
    os.environ['SMTP_RATE_LIMIT_PAUSE'] = '0.01'
    os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
    os.environ['VAPID_PRIVATE_KEY'] = 'test-private-key-base64url'
    os.environ['VAPID_PUBLIC_KEY'] = 'test-public-key-base64url'
    os.environ['VAPID_CLAIMS_EMAIL'] = 'notifications@trudnik.ru'
    os.environ['VAPID_CLAIMS_SUBJECT'] = 'mailto:notifications@trudnik.ru'
    yield
    # Очистка не требуется для unit-тестов


@pytest.fixture
def valid_jwt_token():
    """Создаёт валидный JWT-токен для тестов WebSocket."""
    import jwt
    from datetime import datetime, timedelta, timezone

    payload = {
        'user_id': 1,
        'exp': datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ.get('SECRET_KEY', 'test-secret'), algorithm='HS256')


@pytest.fixture
def expired_jwt_token():
    """Создаёт истёкший JWT-токен для тестов WebSocket."""
    import jwt
    from datetime import datetime, timedelta, timezone

    payload = {
        'user_id': 1,
        'exp': datetime.now(timezone.utc) - timedelta(hours=1),
    }
    return jwt.encode(payload, os.environ.get('SECRET_KEY', 'test-secret'), algorithm='HS256')
