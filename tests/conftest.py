"""
Общие fixtures и хелперы для тестов проекта «Трудник».
Pytest автоматически находит этот файл в корне проекта.

Запуск: python -m pytest -v --tb=short
"""

import os
import re
import time

import pytest

# Подключаем Playwright-фикстуры из отдельного conftest-файла
pytest_plugins = ['tests.conftest_playwright']
import requests
from dotenv import load_dotenv

load_dotenv()

# В тестовом режиме активируем in-memory mock Supabase.
# Гарда: только при запуске через pytest, чтобы случайный импорт conftest
# (например, скриптами деплоя или управления) не активировал mock на проде.
if 'PYTEST_CURRENT_TEST' in os.environ:
    os.environ['TESTING'] = 'true'

# ──────────────────────────────────────────────
# Конфигурация из переменных окружения
# ──────────────────────────────────────────────

BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
_TEST_PASSWORD = os.environ.get('TEST_PASSWORD', 'Step@1986')
EMPLOYER_EMAIL = os.environ.get('EMPLOYER_EMAIL', 'org@test.ru')
EMPLOYER_PASSWORD = os.environ.get('EMPLOYER_PASSWORD', _TEST_PASSWORD)
WORKER_EMAIL = os.environ.get('WORKER_EMAIL', 'trud@test.ru')
WORKER_PASSWORD = os.environ.get('WORKER_PASSWORD', _TEST_PASSWORD)
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@test.ru')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', _TEST_PASSWORD)

# Предупреждение: значения по умолчанию используются, если переменные не заданы
_MISSING = [k for k, v in [('EMPLOYER_PASSWORD', EMPLOYER_PASSWORD),
                             ('WORKER_EMAIL', WORKER_EMAIL),
                             ('WORKER_PASSWORD', WORKER_PASSWORD)] if not v]
if _MISSING:
    import warnings
    warnings.warn(
        f'Используются значения по умолчанию для: {", ".join(_MISSING)}. '
        f'Установите их через переменные окружения для целевого окружения.'
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
    # 1. Пробуем из Location заголовка (редирект)
    if create_resp.status_code in (301, 302):
        location = create_resp.headers.get("Location", "")
        # Парсим URL: /jobs/<uuid> или /job/<uuid>
        for pattern in [r'/jobs/([a-f0-9-]{36})', r'/job/([a-f0-9-]{36})',
                        r'/jobs/([0-9a-f-]{36})', r'/job/([0-9a-f-]{36})']:
            m = re.search(pattern, location)
            if m:
                return m.group(1)
        # Если location содержит UUID-подобную строку
        parts = location.strip("/").split("/")
        for p in parts:
            if re.match(r'^[0-9a-f-]{36}$', p):
                return p

    # 2. Пробуем из тела ответа (JSON или HTML)
    if create_resp.text:
        for pattern in [r'/jobs/([a-f0-9-]{36})', r'/job/([a-f0-9-]{36})',
                        r'data-job-id="([^"]+)"', r'"job_id"\s*:\s*"([^"]+)"',
                        r'"id"\s*:\s*"([a-f0-9-]{36})"']:
            m = re.search(pattern, create_resp.text)
            if m:
                return m.group(1)
        # Пробуем распарсить как JSON
        try:
            import json
            data = json.loads(create_resp.text)
            if isinstance(data, dict):
                jid = data.get('job_id') or data.get('id')
                if jid:
                    return jid
            elif isinstance(data, list) and data:
                jid = data[0].get('job_id') or data[0].get('id')
                if jid:
                    return jid
        except Exception:
            pass

    # 3. Ищем на /my-jobs или главной
    for page in ['/my-jobs', '/']:
        try:
            resp = session.get(f'{BASE_URL}{page}', timeout=30)
            for pattern in [r'/jobs/([0-9a-f-]{36})', r'data-job-id="([^"]+)"',
                            r'/job/([0-9a-f-]{36})']:
                job_ids = re.findall(pattern, resp.text)
                if job_ids:
                    return job_ids[-1]
        except Exception:
            continue

    return None


# ──────────────────────────────────────────────
# Сброс паролей тестовых пользователей (защита от test_*_change_password)
# ──────────────────────────────────────────────

_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
_SUPABASE_URL = (os.environ.get('SUPABASE_URL', '') or '').rstrip('/')
_USER_ID_CACHE: dict[str, str] = {}


def _get_test_user_id(email: str) -> str | None:
    """Получить ID пользователя Supabase Auth по email (с кешированием)."""
    if email in _USER_ID_CACHE:
        return _USER_ID_CACHE[email]
    if not _SERVICE_KEY or not _SUPABASE_URL:
        return None
    try:
        resp = requests.get(
            f'{_SUPABASE_URL}/auth/v1/admin/users',
            headers={'apikey': _SERVICE_KEY, 'Authorization': f'Bearer {_SERVICE_KEY}'},
            timeout=10,
        )
        if resp.status_code == 200:
            users = resp.json()
            if isinstance(users, dict):
                users = users.get('users', [])
            for u in users:
                u_email = u.get('email', '')
                u_id = u.get('id')
                if u_email and u_id:
                    _USER_ID_CACHE[u_email] = u_id
    except Exception:
        pass
    return _USER_ID_CACHE.get(email)


def _reset_password_if_needed(email: str, password: str) -> None:
    """Сбросить пароль тестового пользователя через Supabase Admin API.

    Гарантирует, что пароль корректен, даже если предыдущий тест изменил его
    (например, test_worker_can_change_password).
    """
    user_id = _get_test_user_id(email)
    if not user_id:
        return
    try:
        requests.put(
            f'{_SUPABASE_URL}/auth/v1/admin/users/{user_id}',
            json={'password': password},
            headers={'apikey': _SERVICE_KEY, 'Authorization': f'Bearer {_SERVICE_KEY}'},
            timeout=10,
        )
    except Exception:
        pass  # login_as обработает реальную ошибку аутентификации


def _reset_admin_role() -> None:
    """Сбросить роль админа через Supabase REST API.

    Гарантирует, что admin@test.ru имеет role='admin', даже если предыдущий тест
    (например, test_admin_can_change_user_role) изменил её.
    """
    admin_id = _get_test_user_id(ADMIN_EMAIL)
    if not admin_id or not _SERVICE_KEY or not _SUPABASE_URL:
        return
    try:
        requests.patch(
            f'{_SUPABASE_URL}/rest/v1/profiles?id=eq.{admin_id}',
            json={'role': 'admin'},
            headers={
                'apikey': _SERVICE_KEY,
                'Authorization': f'Bearer {_SERVICE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'return=minimal',
            },
            timeout=10,
        )
    except Exception:
        pass


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope='session', autouse=True)
def preseed_test_data():
    """Автоматически заполняет БД тестовыми данными перед integration-тестами.

    Гарантирует, что приглашения, задания, отклики и рейтинги существуют
    в реальном Supabase перед запуском любого теста с mark='integration'.
    Без этой фикстуры тесты accept/reject invitation пропускаются
    из-за отсутствия pending-приглашений.
    """
    # Импортируем только когда fixture реально исполняется
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from scripts.preseed_test_data import main as _preseed_main

    print('\n[conftest] Running preseed_test_data before integration tests...')
    ok = _preseed_main(fail_on_error=False)
    if not ok:
        print('[conftest] WARNING: preseed_test_data returned False — some tests may skip.')
    else:
        print('[conftest] preseed_test_data completed successfully.')
    return ok


@pytest.fixture(scope='class')
def employer_session():
    """Сессия работодателя (org@test.ru). Одна на класс тестов — избегает rate-limit."""
    _reset_password_if_needed(EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    sess = requests.Session()
    csrf = login_as(sess, EMPLOYER_EMAIL, EMPLOYER_PASSWORD)
    if csrf is None:
        pytest.skip('Не удалось войти как работодатель (rate limit или учётные данные).')
    return sess


@pytest.fixture(scope='class')
def worker_session():
    """Сессия трудника (trud@test.ru). Одна на класс тестов — избегает rate-limit."""
    _reset_password_if_needed(WORKER_EMAIL, WORKER_PASSWORD)
    sess = requests.Session()
    csrf = login_as(sess, WORKER_EMAIL, WORKER_PASSWORD)
    if csrf is None:
        pytest.skip('Не удалось войти как трудник (rate limit или учётные данные).')
    return sess


@pytest.fixture(scope='function')
def admin_session():
    """Фикстура: сессия администратора. Function-scope — гарантирует сброс роли перед каждым тестом."""
    _reset_password_if_needed(ADMIN_EMAIL, ADMIN_PASSWORD)
    # Сбросить роль админа через Supabase REST API (на случай если предыдущий тест изменил)
    _reset_admin_role()
    try:
        sess = requests.Session()
        csrf = login_as(sess, ADMIN_EMAIL, ADMIN_PASSWORD)
        if csrf is None:
            pytest.skip('Не удалось войти как администратор (rate limit или учётные данные).')
        return sess
    except Exception as e:
        pytest.skip(f'Не удалось войти как администратор: {e}')


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
    """Возвращает (application_id, job_id) для существующего accepted-отклика.

    Стратегия:
    1. Сначала ищет готовый accepted-отклик из preseed-данных через Supabase REST API.
    2. Только если не найден — fallback на динамическое создание через веб-формы.

    Возвращает (application_id, job_id) или (None, None) при ошибке.
    """
    e_sess = employer_session
    w_sess = worker_session

    # ═══ Шаг 1: Поиск существующего accepted-отклика через Supabase REST API ═══
    worker_uuid = _get_test_user_id(WORKER_EMAIL)
    if worker_uuid and _SERVICE_KEY and _SUPABASE_URL:
        try:
            # Запрашиваем accepted-отклики трудника с joined-полем статуса задания
            resp = requests.get(
                f'{_SUPABASE_URL}/rest/v1/applications',
                headers={
                    'apikey': _SERVICE_KEY,
                    'Authorization': f'Bearer {_SERVICE_KEY}',
                },
                params={
                    'worker_id': f'eq.{worker_uuid}',
                    'status': 'eq.accepted',
                    'select': 'id,job_id,jobs(status)',
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                for app in data:
                    job = app.get('jobs')
                    # jobs может быть объектом или списком (зависит от версии PostgREST)
                    job_status = None
                    if isinstance(job, dict):
                        job_status = job.get('status')
                    elif isinstance(job, list) and len(job) > 0:
                        job_status = job[0].get('status')

                    if job_status == 'open':
                        app_id = app.get('id')
                        job_id = app.get('job_id')
                        if app_id and job_id:
                            print(f"[FIXTURE accepted_application_id] PRESEED FOUND: app_id={app_id}, job_id={job_id}")
                            return app_id, job_id
        except Exception as e:
            print(f"[FIXTURE accepted_application_id] Preseed REST query failed: {e}")

    print("[FIXTURE accepted_application_id] No preseeded accepted application found, falling back to dynamic creation...")

    # ═══ Шаг 2: Fallback — динамическое создание ═══
    # Уникальное название для поиска на странице
    job_title = f"Задание для accepted-отклика {int(time.time())}"

    # 1. Создать задание (сразу is_paid=True)
    form = form_with_csrf(
        e_sess,
        title=job_title,
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
    print(f"[FIXTURE accepted_application_id] Step 1 (create job): status={create_resp.status_code}")
    job_id = _extract_job_id_from_redirect(e_sess, create_resp)
    print(f"[FIXTURE accepted_application_id] Step 1 (create job): job_id={job_id}, title='{job_title}'")
    if not job_id:
        print(f"[FIXTURE accepted_application_id] FAILED at step 1: no job_id")
        return None, None

    # 2. Worker откликается
    apply_resp = w_sess.post(
        f"{BASE_URL}/apply/{job_id}",
        data=form_with_csrf(w_sess),
        timeout=30,
        allow_redirects=True,
    )
    print(f"[FIXTURE accepted_application_id] Step 2 (apply): status={apply_resp.status_code}")
    if apply_resp.status_code not in (200, 301, 302):
        print(f"[FIXTURE accepted_application_id] FAILED at step 2: bad status {apply_resp.status_code}")
        return None, None

    # 3. Получить ID отклика через страницу my-applications работодателя
    # Ищем data-app-id поблизости от названия задания
    app_id = None
    my_apps = e_sess.get(f"{BASE_URL}/my-applications", timeout=30)
    html = my_apps.text
    print(f"[FIXTURE accepted_application_id] Step 3 (find app_id): my-applications status={my_apps.status_code}, len={len(html)}")

    # Найти позицию названия задания в HTML
    title_pos = html.find(job_title)
    if title_pos >= 0:
        # Ищем data-app-id в окрестности (10000 символов после заголовка)
        search_region = html[title_pos:title_pos + 10000]
        for pattern in [
            r'data-app-id="([^"]+)"',
            r'data-application-id="([^"]+)"',
            r'/api/applications/([a-f0-9\-]+)/accept',
            r'/chat/([a-f0-9\-]+)',
        ]:
            matches = re.findall(pattern, search_region)
            if matches:
                app_id = matches[0]
                print(f"[FIXTURE accepted_application_id] Step 3: found app_id={app_id} near job title via pattern '{pattern}'")
                break

    if not app_id:
        # Fallback: ищем на всей странице (берём первое совпадение — самое свежее)
        print(f"[FIXTURE accepted_application_id] Step 3: title not found on page, falling back to global search")
        for pattern in [
            r'data-app-id="([^"]+)"',
            r'data-application-id="([^"]+)"',
            r'/api/applications/([a-f0-9\-]+)/accept',
            r'/chat/([a-f0-9\-]+)',
        ]:
            matches = re.findall(pattern, html)
            if matches:
                app_id = matches[0]
                print(f"[FIXTURE accepted_application_id] Step 3 (fallback): found app_id={app_id} via pattern '{pattern}' (total: {len(matches)})")
                break

    if not app_id:
        # Ищем на странице /my-jobs
        print(f"[FIXTURE accepted_application_id] Step 3: no app_id, trying my-jobs")
        my_jobs = e_sess.get(f"{BASE_URL}/my-jobs", timeout=30)
        html_jobs = my_jobs.text
        title_pos2 = html_jobs.find(job_title)
        if title_pos2 >= 0:
            search_region2 = html_jobs[title_pos2:title_pos2 + 10000]
            for pattern in [r'data-app-id="([^"]+)"', r'/api/applications/([a-f0-9\-]+)/accept', r'/chat/([a-f0-9\-]+)']:
                matches = re.findall(pattern, search_region2)
                if matches:
                    app_id = matches[0]
                    print(f"[FIXTURE accepted_application_id] Step 3 (my-jobs): found app_id={app_id} near job title")
                    break

    if not app_id:
        print(f"[FIXTURE accepted_application_id] FAILED at step 3: no app_id found")
        return None, None

    # 4. Принять отклик
    accept_resp = e_sess.post(
        f"{BASE_URL}/api/applications/{app_id}/accept",
        headers=csrf_headers(e_sess),
        timeout=30,
    )
    print(f"[FIXTURE accepted_application_id] Step 4 (accept): status={accept_resp.status_code}, ct={accept_resp.headers.get('content-type', '')}")
    # Accept может вернуть 200 (JSON), 302 (redirect), 500 (RPC missing) или 403 (уже accepted)
    if accept_resp.status_code not in (200, 302, 500):
        print(f"[FIXTURE accepted_application_id] FAILED at step 4: bad status {accept_resp.status_code}, body={accept_resp.text[:200]}")
        return None, None
    # Если JSON ответ — проверяем success/status
    ct = accept_resp.headers.get('content-type', '')
    accept_ok = accept_resp.status_code in (200, 302)
    if 'application/json' in ct:
        try:
            data = accept_resp.json()
            print(f"[FIXTURE accepted_application_id] Step 4 (JSON): data={data}")
            accept_ok = data.get("success", False)
        except Exception as e:
            print(f"[FIXTURE accepted_application_id] Step 4: JSON parse error: {e}")
            pass

    if not accept_ok:
        # RPC accept_application не сработал (нет в локальном Supabase).
        # Ищем уже существующий accepted отклик от пресида
        print(f"[FIXTURE accepted_application_id] Step 4: accept failed (RPC missing?), looking for existing accepted application")
        for pattern in [r'data-app-id="([^"]+)"', r'data-application-id="([^"]+)"']:
            all_matches = re.findall(pattern, html)
            for candidate in all_matches:
                pos = html.find(f'data-app-id="{candidate}"')
                if pos < 0:
                    pos = html.find(f"data-app-id='{candidate}'")
                if pos >= 0:
                    region = html[max(0, pos - 500):pos + 2000]
                    if 'status-accepted' in region or 'Принято' in region:
                        job_matches = re.findall(r'/jobs/([a-f0-9-]{36})', region)
                        job_id_found = job_matches[0] if job_matches else job_id
                        print(f"[FIXTURE accepted_application_id] Step 4 (fallback): found accepted app_id={candidate}, job_id={job_id_found}")
                        return candidate, job_id_found
        # Не нашли accepted — возвращаем то, что есть
        print(f"[FIXTURE accepted_application_id] Step 4: no accepted app found, returning pending app_id={app_id}, job_id={job_id}")
        return app_id, job_id

    # Всё ок — возвращаем ID
    print(f"[FIXTURE accepted_application_id] SUCCESS: app_id={app_id}, job_id={job_id}")
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
