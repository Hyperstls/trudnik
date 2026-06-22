"""In-Memory Mock для тестового режима (TESTING=True).

Вынесен из app/utils.py для улучшения структуры кода.
Обеспечивает полную эмуляцию PostgREST REST API, Auth, RPC для тестов.
"""
import json
import logging
import os
import uuid
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import Config

logger = logging.getLogger(__name__)

# =============================================================
# Ленивый импорт SupabaseResponse из app.utils (избегаем circular import)
# =============================================================

_SupabaseResponse = None

def _get_supabase_response_class():
    """Ленивый импорт SupabaseResponse для избежания circular import."""
    global _SupabaseResponse
    if _SupabaseResponse is None:
        from app.utils import SupabaseResponse
        _SupabaseResponse = SupabaseResponse
    return _SupabaseResponse

# In-Memory Mock для тестового режима (TESTING=True)
# ═══════════════════════════════════════════════════════════════

_test_db: dict[str, list[dict]] = {}  # table_name -> list of records
_uuid_counter = 0


def _gen_uuid() -> str:
    """Генерирует детерминированный UUID v4 на основе счётчика."""
    global _uuid_counter
    _uuid_counter += 1
    # Используем uuid.UUID(int=...) для гарантии RFC 4122 совместимости
    return str(uuid.UUID(int=_uuid_counter))


# ═══════════════════════════════════════════════════════════════
# Auth mock: перехватывает прямые вызовы requests к Auth API
# ═══════════════════════════════════════════════════════════════

_test_auth_tokens: dict[str, dict] = {}  # token -> user profile

# Сохраняем оригинальные функции
_original_post = requests.post
_original_get = requests.get
_original_delete = requests.delete
_original_patch = requests.patch
_original_put = requests.put

_test_password_warned = False


class _MockRequestsResponse:
    """Mock-ответ, совместимый с requests.Response для auth-вызовов."""
    def __init__(self, status_code: int, data: Any):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_data = data
        self.text = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
        self.headers = {'Content-Type': 'application/json'}
        self._content = self.text.encode('utf-8')

    def json(self) -> Any:
        return self._json_data


def _should_intercept(url: str) -> bool:
    """Проверить, нужно ли перехватывать этот URL."""
    postgrest_url = Config.POSTGREST_URL.rstrip('/')
    return url.startswith(postgrest_url) and '/auth/v1/' in url


def _mock_post(url: str, *args: Any, **kwargs: Any) -> Any:
    """Перехватывает requests.post для Auth API."""
    if not _should_intercept(url):
        return _original_post(url, *args, **kwargs)

    postgrest_url = Config.POSTGREST_URL.rstrip('/')
    path = url[len(postgrest_url):].lstrip('/')

    # POST auth/v1/token?grant_type=password (логин)
    if path.startswith('auth/v1/token'):
        parsed = urllib.parse.urlparse(url)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        grant_type = params.get('grant_type', '')
        body = kwargs.get('json', {})

        if grant_type == 'password':
            email = body.get('email', '')
            password = body.get('password', '')
            for p in _test_db.get('profiles', []):
                if p.get('email') == email:
                    if not os.environ.get('TEST_PASSWORD'):
                        global _test_password_warned
                        if not _test_password_warned:
                            _test_password_warned = True
                            logger.warning(
                                "TEST_PASSWORD not set in environment. "
                                "Mock auth will reject ALL login attempts. "
                                "Set TEST_PASSWORD env var to enable test logins."
                            )
                    if password and password == os.environ.get('TEST_PASSWORD', ''):
                        token = f'mock-access-{p["id"][:8]}'
                        refresh = f'mock-refresh-{p["id"][:8]}'
                        _test_auth_tokens[token] = p
                        return _MockRequestsResponse(200, {
                            'access_token': token,
                            'refresh_token': refresh,
                            'token_type': 'bearer',
                            'user': {'id': p['id'], 'email': email, 'role': p.get('role', 'worker')}
                        })
                    else:
                        return _MockRequestsResponse(400, {'error': 'Invalid login credentials'})
            return _MockRequestsResponse(400, {'error': 'Invalid login credentials'})

        elif grant_type == 'refresh_token':
            return _MockRequestsResponse(200, {
                'access_token': 'mock-refreshed-access-token',
                'refresh_token': kwargs.get('json', {}).get('refresh_token', 'mock-refresh'),
            })

    # POST auth/v1/signup (регистрация)
    if path == 'auth/v1/signup':
        body = kwargs.get('json', {})
        email = body.get('email', '')
        password = body.get('password', '')
        if not email:
            return _MockRequestsResponse(400, {'msg': 'Email required'})
        for p in _test_db.get('profiles', []):
            if p.get('email') == email:
                return _MockRequestsResponse(400, {'msg': 'User already registered'})
        user_id = _gen_uuid()
        new_profile = {
            'id': user_id, 'full_name': '', 'email': email,
            'role': 'worker', 'photo_url': '', 'rating': 0,
            'skills': [], 'desired_payment': 0, 'inn': '',
            'phone': '', 'email_public': email,
        }
        _test_db.setdefault('profiles', []).append(new_profile)
        return _MockRequestsResponse(200, {
            'access_token': f'mock-access-{user_id[:8]}',
            'token_type': 'bearer',
            'user': {'id': user_id, 'email': email},
        })

    return _original_post(url, *args, **kwargs)


def _mock_delete(url: str, *args: Any, **kwargs: Any) -> Any:
    """Перехватывает requests.delete для Auth API."""
    if not _should_intercept(url):
        return _original_delete(url, *args, **kwargs)
    postgrest_url = Config.POSTGREST_URL.rstrip('/')
    path = url[len(postgrest_url):].lstrip('/')
    if path.startswith('auth/v1/admin/users/'):
        return _MockRequestsResponse(200, {})
    return _original_delete(url, *args, **kwargs)


def _install_auth_mock():
    """Установить перехватчики requests для auth-эндпоинтов и Celery-заглушки."""
    requests.post = _mock_post
    requests.delete = _mock_delete
    # Mock Celery delay() и apply_async() чтобы избежать таймаутов при отсутствии Redis
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
    # Mock Redis publisher чтобы избежать блокировок при отсутствии Redis
    try:
        from app.services.redis_publisher import RedisPublisher
        RedisPublisher.publish = lambda self, channel, message: None
        RedisPublisher.publish_notification = lambda self, *a, **kw: False
        RedisPublisher.publish_chat_message = lambda self, *a, **kw: False
        RedisPublisher._get_client = lambda self: None
        RedisPublisher.__init__ = lambda self, *a, **kw: None
    except Exception:
        pass


def _uninstall_auth_mock():
    """Восстановить оригинальные функции requests."""
    requests.post = _original_post
    requests.get = _original_get
    requests.delete = _original_delete
    requests.patch = _original_patch
    requests.put = _original_put


def _is_mock_enabled() -> bool:
    """Проверить, активен ли in-memory mock PostgREST.

    Приоритет проверок:
    1. Переменная окружения SUPABASE_MOCK_MODE (явный opt-in для скриптов)
    2. Flask-конфигурация TESTING=True (тестовый режим)
    3. Файл .mock_supabase в корне проекта (legacy, только для CI/скриптов)

    Ни одна из проверок не срабатывает случайно в production.
    """
    # Явный opt-in через переменную окружения
    if os.environ.get('SUPABASE_MOCK_MODE', '').lower() in ('1', 'true', 'yes'):
        return True

    # Flask-конфигурация TESTING (устанавливается в conftest.py)
    try:
        from flask import current_app as _current_app
        if _current_app and _current_app.config.get('TESTING'):
            return True
    except (RuntimeError, ImportError):
        pass

    # Legacy: файл .mock_supabase для CI/скриптов вне Flask-контекста
    # Файл должен быть явно создан — случайное попадание исключено .gitignore
    if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.mock_supabase')):
        return True

    return False


# Устанавливаем перехватчик, если mock включён
if _is_mock_enabled():
    _install_auth_mock()


def _test_mock_request(method: str, endpoint: str, **kwargs: Any) -> SupabaseResponse:
    """Обрабатывает HTTP-запрос локально при TESTING=True."""
    global _test_db

    # Парсим endpoint: 'jobs?status=eq.open&select=id,title'
    if '?' in endpoint:
        table, query_string = endpoint.split('?', 1)
    else:
        table = endpoint
        query_string = ''

    if table not in _test_db:
        _test_db[table] = []

    records = _test_db[table]

    # Парсим фильтры
    # PostgREST URL формат: column=operator.value
    # Примеры:
    #   id=eq.abc123            → equality: id == abc123
    #   status=not.is.null      → not null: status IS NOT NULL
    #   full_name=ilike.*Иван*  → ilike: full_name ILIKE '%Иван%'
    #   id=in.(a,b,c)           → in: id IN (a, b, c)
    #   payment_amount=gte.500  → >=
    #   payment_amount=lte.1000 → <=
    #   created_at=gt.2025-01-01 → >
    #   message=not.ilike.*спам* → NOT ILIKE
    filters: dict[str, Any] = {}
    not_null_filters: list[str] = []
    is_null_filters: list[str] = []
    ilike_filters: dict[str, str] = {}
    not_ilike_filters: dict[str, str] = {}
    in_filters: dict[str, list[str]] = {}
    gte_filters: dict[str, str] = {}
    lte_filters: dict[str, str] = {}
    gt_filters: dict[str, str] = {}
    lt_filters: dict[str, str] = {}
    select_fields = None
    order_field = None
    order_desc = False
    limit_count = None
    offset_count = 0
    has_or_filter = False  # or=(...) — сложный фильтр, возвращаем все записи
    if query_string:
        for part in query_string.split('&'):
            if '=' not in part:
                continue
            k, v = part.split('=', 1)
            if k == 'select':
                select_fields = v.split(',')
            elif k == 'order':
                if v.endswith('.desc'):
                    order_field = v[:-5]
                    order_desc = True
                elif v.endswith('.asc'):
                    order_field = v[:-4]
                    order_desc = False
                else:
                    order_field = v
            elif k == 'limit':
                try:
                    limit_count = int(v)
                except ValueError:
                    pass
            elif k == 'offset':
                try:
                    offset_count = int(v)
                except ValueError:
                    pass
            elif k == 'or':
                has_or_filter = True
            elif v.startswith('eq.'):
                filters[k] = v[3:]
            elif v.startswith('gte.'):
                gte_filters[k] = v[4:]
            elif v.startswith('lte.'):
                lte_filters[k] = v[4:]
            elif v.startswith('gt.'):
                gt_filters[k] = v[3:]
            elif v.startswith('lt.'):
                lt_filters[k] = v[3:]
            elif v.startswith('not.is.null'):
                not_null_filters.append(k)
            elif v.startswith('is.null'):
                is_null_filters.append(k)
            elif v.startswith('not.ilike.'):
                pattern = v[10:].strip('*')
                not_ilike_filters[k] = pattern
            elif v.startswith('ilike.'):
                pattern = v[6:].strip('*')
                ilike_filters[k] = pattern
            elif v.startswith('in.('):
                val = v[3:].strip('()')
                in_filters[k] = [x.strip() for x in val.split(',') if x.strip()]
            elif k in ('offset',):
                pass  # Уже обработано выше
            else:
                filters[k] = v

    # GET — возвращаем записи по фильтру
    if method == 'GET':
        # or=(...) — сложный фильтр, в моке возвращаем все записи (фильтрация в Python-коде)
        if has_or_filter:
            result = list(records)
        else:
            result = []
            for r in records:
                match = True
                # Equality filters
                for col, val in filters.items():
                    if str(r.get(col, '')) != str(val):
                        match = False
                        break
                if not match:
                    continue
                # gte (>=)
                for col, val in gte_filters.items():
                    try:
                        if float(r.get(col, 0)) < float(val):
                            match = False
                            break
                    except (ValueError, TypeError):
                        if str(r.get(col, '')) < str(val):
                            match = False
                            break
                if not match:
                    continue
                # lte (<=)
                for col, val in lte_filters.items():
                    try:
                        if float(r.get(col, 0)) > float(val):
                            match = False
                            break
                    except (ValueError, TypeError):
                        if str(r.get(col, '')) > str(val):
                            match = False
                            break
                if not match:
                    continue
                # gt (>)
                for col, val in gt_filters.items():
                    try:
                        if float(r.get(col, 0)) <= float(val):
                            match = False
                            break
                    except (ValueError, TypeError):
                        if str(r.get(col, '')) <= str(val):
                            match = False
                            break
                if not match:
                    continue
                # lt (<)
                for col, val in lt_filters.items():
                    try:
                        if float(r.get(col, 0)) >= float(val):
                            match = False
                            break
                    except (ValueError, TypeError):
                        if str(r.get(col, '')) >= str(val):
                            match = False
                            break
                if not match:
                    continue
                # not.is.null
                for col in not_null_filters:
                    if r.get(col) is None:
                        match = False
                        break
                if not match:
                    continue
                # is.null
                for col in is_null_filters:
                    if r.get(col) is not None:
                        match = False
                        break
                if not match:
                    continue
                # not.ilike (case-insensitive NOT contains)
                for col, pattern in not_ilike_filters.items():
                    val = str(r.get(col, '')).lower()
                    if pattern.lower() in val:
                        match = False
                        break
                if not match:
                    continue
                # ilike (case-insensitive contains)
                for col, pattern in ilike_filters.items():
                    val = str(r.get(col, '')).lower()
                    if pattern.lower() not in val:
                        match = False
                        break
                if not match:
                    continue
                # in filter
                for col, vals in in_filters.items():
                    if str(r.get(col, '')) not in vals:
                        match = False
                        break
                if not match:
                    continue
                result.append(r)

        # Сортировка
        if order_field:
            result.sort(key=lambda x: str(x.get(order_field, '')), reverse=order_desc)

        # Offset (пропускаем записи)
        if offset_count > 0:
            result = result[offset_count:]

        # Лимит
        if limit_count is not None:
            result = result[:limit_count]

        # select — возвращаем только указанные поля
        if select_fields:
            plain_fields = []
            embed_fields: dict[str, list] = {}
            embed_counts: dict[str, list] = {}
            for sf in select_fields:
                if ':' in sf and '(' in sf:
                    # PostgREST embedded resource: photos:job_photos(*) or applications:applications(count)
                    alias, rest = sf.split(':', 1)
                    if '(count)' in rest:
                        embed_counts[alias] = [{'count': 0}]
                    else:
                        embed_fields[alias] = []
                elif sf == '*':
                    pass  # Will be handled below
                else:
                    plain_fields.append(sf)

            if plain_fields or '*' in select_fields:
                if '*' in select_fields:
                    result = [dict(r) for r in result]
                else:
                    result = [{k: r.get(k) for k in plain_fields if k in r} for r in result]

            # Добавляем placeholder-ы для embedded resources
            if embed_fields:
                for r in result:
                    for alias in embed_fields:
                        r[alias] = []
            # Добавляем count placeholder-ы
            if embed_counts:
                for r in result:
                    for alias, val in embed_counts.items():
                        r[alias] = val

        return _get_supabase_response_class()(ok=True, status_code=200, data=result, text=json.dumps(result))

    # POST — создаём запись
    elif method == 'POST':
        data = kwargs.get('json', {})
        new_record = dict(data)
        if 'id' not in new_record:
            new_record['id'] = _gen_uuid()
        records.append(new_record)
        return _get_supabase_response_class()(ok=True, status_code=201, data=[new_record], text=json.dumps([new_record]))

    # PATCH — обновляем по id или фильтру
    elif method == 'PATCH':
        data = kwargs.get('json', {})
        updated = []
        for r in records:
            match = True
            for col, val in filters.items():
                if str(r.get(col, '')) != str(val):
                    match = False
                    break
            if match:
                r.update(data)
                updated.append(r)
        return _get_supabase_response_class()(ok=True, status_code=200, data=updated, text=json.dumps(updated))

    # DELETE — удаляем по фильтру
    elif method == 'DELETE':
        to_delete = []
        remaining = []
        for r in records:
            match = True
            for col, val in filters.items():
                if str(r.get(col, '')) != str(val):
                    match = False
                    break
            if match:
                to_delete.append(r)
            else:
                remaining.append(r)
        _test_db[table] = remaining
        return _get_supabase_response_class()(ok=True, status_code=204, data=to_delete, text='')

    return _get_supabase_response_class()(ok=False, status_code=405, text=f'Method {method} not supported in mock')


def _test_mock_rpc(function_name: str, params: dict) -> SupabaseResponse:
    """Обрабатывает RPC-вызов локально при TESTING=True.

    ВАЖНО: все RPC возвращают data как dict (не list), потому что код приложения
    ожидает result.json().get('success'), а не result.json()[0].get('success').
    """
    # accept_application / reject_application — меняем статус заявки
    if function_name in ('accept_application', 'reject_application'):
        app_id = params.get('p_app_id', '')
        job_id = params.get('p_job_id', '')
        new_status = 'accepted' if function_name == 'accept_application' else 'rejected'

        for app in _test_db.get('applications', []):
            if app.get('id') == app_id:
                app['status'] = new_status

        # Обновляем счётчик в задании
        for job in _test_db.get('jobs', []):
            if job.get('id') == job_id:
                if new_status == 'accepted':
                    job['current_workers'] = job.get('current_workers', 0) + 1
                    if job['current_workers'] >= job.get('max_workers', 99):
                        job['status'] = 'completed'
                else:
                    job['current_workers'] = max(0, job.get('current_workers', 1) - 1)

        return _get_supabase_response_class()(ok=True, status_code=200, data={'success': True, 'status': new_status}, text=json.dumps({'success': True, 'status': new_status}))

    # apply_job_atomic — создаём отклик
    if function_name == 'apply_job_atomic':
        job_id = params.get('p_job_id', '')
        worker_id = params.get('p_worker_id', '')
        # Проверка дубликата
        for a in _test_db.get('applications', []):
            if a.get('job_id') == job_id and a.get('worker_id') == worker_id:
                return _get_supabase_response_class()(ok=True, status_code=200, data={'success': False, 'code': 'duplicate', 'error': 'Вы уже откликались на это задание'}, text=json.dumps({'success': False, 'code': 'duplicate', 'error': 'Вы уже откликались на это задание'}))
        # Проверка мест
        for j in _test_db.get('jobs', []):
            if j.get('id') == job_id:
                if j.get('current_workers', 0) >= j.get('max_workers', 99):
                    return _get_supabase_response_class()(ok=True, status_code=200, data={'success': False, 'code': 'no_slots', 'error': 'Нет свободных мест'}, text=json.dumps({'success': False, 'code': 'no_slots', 'error': 'Нет свободных мест'}))
                employer_id = j.get('employer_id', '')
                break
        else:
            employer_id = ''
        new_app = {
            'id': _gen_uuid(),
            'job_id': job_id,
            'worker_id': worker_id,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        _test_db.setdefault('applications', []).append(new_app)
        return _get_supabase_response_class()(ok=True, status_code=200, data={'success': True, 'id': new_app['id'], 'employer_id': employer_id}, text=json.dumps({'success': True, 'id': new_app['id'], 'employer_id': employer_id}))

    # delete_job_cascade — удаление задания и связанных записей
    if function_name == 'delete_job_cascade':
        job_id = params.get('p_job_id', '')
        _test_db['jobs'] = [j for j in _test_db.get('jobs', []) if j.get('id') != job_id]
        _test_db['applications'] = [a for a in _test_db.get('applications', []) if a.get('job_id') != job_id]
        _test_db['messages'] = [m for m in _test_db.get('messages', []) if m.get('job_id') != job_id]
        return _get_supabase_response_class()(ok=True, status_code=200, data={'success': True}, text=json.dumps({'success': True}))

    # delete_user_cascade — удаление пользователя и связанных записей
    if function_name == 'delete_user_cascade':
        user_id = params.get('p_user_id', '')
        _test_db['profiles'] = [p for p in _test_db.get('profiles', []) if p.get('id') != user_id]
        _test_db['jobs'] = [j for j in _test_db.get('jobs', []) if j.get('employer_id') != user_id]
        _test_db['applications'] = [a for a in _test_db.get('applications', []) if a.get('worker_id') != user_id]
        return _get_supabase_response_class()(ok=True, status_code=200, data={'success': True}, text=json.dumps({'success': True}))

    # get_job_stats / get_user_stats / get_dashboard_stats — статистика
    if function_name in ('get_job_stats', 'get_user_stats', 'get_dashboard_stats'):
        return _get_supabase_response_class()(ok=True, status_code=200, data={'total': 0, 'open': 0, 'completed': 0, 'cancelled': 0}, text=json.dumps({'total': 0, 'open': 0, 'completed': 0, 'cancelled': 0}))

    # get_completed_jobs_between — проверка совместных завершённых заданий
    if function_name == 'get_completed_jobs_between':
        return _get_supabase_response_class()(ok=True, status_code=200, data=[], text=json.dumps([]))

    # nearby_jobs — геопоиск заданий в радиусе (возвращает список jobs)
    if function_name == 'nearby_jobs':
        return _get_supabase_response_class()(ok=True, status_code=200, data=[], text=json.dumps([]))

    return _get_supabase_response_class()(ok=False, status_code=404, text=f'RPC {function_name} not mocked')


def _reset_test_db():
    """Очищает тестовую БД."""
    global _test_db, _uuid_counter
    _test_db = {}
    _uuid_counter = 0


def _seed_test_db():
    """Наполняет тестовую БД начальными данными."""
    _reset_test_db()
    # Добавляем профили (нужны для joins)
    employer_id = '00000000-0000-0000-0000-000000000001'
    worker_id = '00000000-0000-0000-0000-000000000002'
    admin_id = '00000000-0000-0000-0000-000000000003'
    _test_db['profiles'] = [
        {'id': employer_id, 'full_name': 'Тестовый Работодатель', 'email': 'org@test.ru', 'role': 'employer', 'photo_url': '', 'rating': 4.5, 'skills': ['Уборка'], 'desired_payment': 0, 'inn': '7700000000', 'phone': '+79000000001', 'email_public': 'org@test.ru', 'verification_status': None, 'updated_at': '2025-01-01T00:00:00+00:00', 'notification_prefs': {'email': True, 'push': True}, 'username': 'test_employer', 'city': 'Москва', 'experience': '5 лет'},
        {'id': worker_id, 'full_name': 'Тестовый Трудник', 'email': 'trud@test.ru', 'role': 'worker', 'photo_url': '', 'rating': 4.0, 'skills': ['Уборка', 'Курьер'], 'desired_payment': 1000, 'inn': '', 'phone': '+79000000002', 'email_public': 'trud@test.ru', 'verification_status': None, 'updated_at': '2025-01-01T00:00:00+00:00', 'notification_prefs': {'email': True, 'push': True}, 'username': 'test_worker', 'city': 'Москва', 'experience': '2 года'},
        {'id': admin_id, 'full_name': 'Админ', 'email': 'admin@test.ru', 'role': 'admin', 'photo_url': '', 'rating': 5.0, 'skills': [], 'desired_payment': 0, 'inn': '', 'phone': '', 'email_public': 'admin@test.ru', 'verification_status': None, 'updated_at': '2025-01-01T00:00:00+00:00', 'notification_prefs': {'email': True, 'push': True}, 'username': 'admin', 'city': 'Москва', 'experience': ''},
    ]
    # Несколько тестовых заданий для админки и страниц
    _test_db['jobs'] = [
        {'id': '00000000-0000-0000-0000-000000000010', 'employer_id': employer_id, 'title': 'Уборка офиса', 'organization_name': 'ООО Тест', 'org_description': 'Клининговая компания', 'object_description': 'Офис 100 кв.м', 'work_type': 'Уборка', 'description': 'Ежедневная уборка', 'detailed_description': '', 'date_time': '2026-07-01T09:00:00', 'payment_amount': 1500, 'address': 'Москва, ул. Тестовая, 1', 'city': 'Москва', 'lat': 55.75, 'lng': 37.61, 'status': 'open', 'max_workers': 2, 'current_workers': 0, 'is_paid': True, 'created_at': '2025-06-01T10:00:00+00:00', 'preferred_religion': '', 'tariff': 'basic', 'expires_at': '2026-12-31T23:59:59+00:00'},
        {'id': '00000000-0000-0000-0000-000000000011', 'employer_id': employer_id, 'title': 'Доставка документов', 'organization_name': 'ИП Иванов', 'org_description': 'Курьерская служба', 'object_description': 'Пакет документов', 'work_type': 'Курьер', 'description': 'Срочная доставка', 'detailed_description': '', 'date_time': '2026-08-15T12:00:00', 'payment_amount': 800, 'address': 'Москва, ул. Деловая, 5', 'city': 'Москва', 'lat': 55.76, 'lng': 37.62, 'status': 'completed', 'max_workers': 1, 'current_workers': 1, 'is_paid': True, 'created_at': '2025-07-01T10:00:00+00:00', 'preferred_religion': '', 'tariff': 'basic', 'expires_at': '2026-12-31T23:59:59+00:00'},
        {'id': '00000000-0000-0000-0000-000000000012', 'employer_id': employer_id, 'title': 'Ремонт розетки', 'organization_name': 'ООО Тест', 'org_description': 'Электромонтаж', 'object_description': 'Замена розетки', 'work_type': 'Электрика', 'description': 'Срочно заменить', 'detailed_description': '', 'date_time': '2026-06-20T14:00:00', 'payment_amount': 500, 'address': 'Москва, ул. Срочная, 3', 'city': 'Москва', 'lat': 55.77, 'lng': 37.63, 'status': 'cancelled', 'max_workers': 1, 'current_workers': 0, 'is_paid': True, 'created_at': '2025-06-15T10:00:00+00:00', 'preferred_religion': '', 'tariff': 'basic', 'expires_at': '2026-12-31T23:59:59+00:00'},
    ]
    _test_db['skills'] = [
        {'id': 'skill-1', 'name': 'Уборка', 'sort_order': 1},
        {'id': 'skill-2', 'name': 'Курьер', 'sort_order': 2},
        {'id': 'skill-3', 'name': 'Электрика', 'sort_order': 3},
    ]
    _test_db['religions'] = [{'id': 'rel-1', 'name': 'Православие', 'sort_order': 1}]
    # verification_requests для админ-тестов
    _test_db['verification_requests'] = [
        {'id': '00000000-0000-0000-0000-000000000020', 'user_id': employer_id, 'company_name': 'ООО Тест', 'inn': '7700000000', 'description': 'Тестовая компания', 'status': 'pending', 'created_at': '2025-06-01T10:00:00+00:00'},
    ]
    # Отклики (applications)
    _test_db['applications'] = [
        {'id': '00000000-0000-0000-0000-000000000030', 'job_id': '00000000-0000-0000-0000-000000000010', 'worker_id': worker_id, 'status': 'pending', 'created_at': '2025-06-02T10:00:00+00:00'},
        {'id': '00000000-0000-0000-0000-000000000031', 'job_id': '00000000-0000-0000-0000-000000000011', 'worker_id': worker_id, 'status': 'accepted', 'created_at': '2025-07-02T10:00:00+00:00'},
    ]
    # Таблицы-заглушки (пустые, но существуют чтобы не было 404)
    _test_db['job_photos'] = []
    _test_db['notification_prefs'] = [
        {'id': '00000000-0000-0000-0000-000000000040', 'user_id': worker_id, 'email_notifications': True, 'push_notifications': True, 'new_job': True, 'status_change': True, 'new_message': True, 'invitation': True},
    ]
    _test_db['chat_rooms'] = []
    _test_db['messages'] = []
    _test_db['favorites'] = []
    _test_db['blacklists'] = [
        {'id': '00000000-0000-0000-0000-000000000060', 'user_id': employer_id, 'blocked_user_id': worker_id, 'created_at': '2025-06-01T10:00:00+00:00'},
    ]
    _test_db['invitations'] = [
        {'id': '00000000-0000-0000-0000-000000000070', 'job_id': '00000000-0000-0000-0000-000000000010', 'employer_id': employer_id, 'worker_id': worker_id, 'status': 'pending', 'created_at': '2025-06-01T10:00:00+00:00'},
    ]
    _test_db['ratings'] = []
    _test_db['job_favorites'] = []
    _test_db['user_skills'] = []
    _test_db['job_skills'] = []
    _test_db['email_log'] = []
    _test_db['push_subscriptions'] = []
    _test_db['notifications'] = [
        {'id': '00000000-0000-0000-0000-000000000050', 'user_id': worker_id, 'type': 'info', 'message': 'Добро пожаловать в Трудник!', 'is_read': False, 'created_at': '2025-06-01T10:00:00+00:00'},
    ]
    # Делаем employer pending verification в profiles
    for p in _test_db['profiles']:
        if p['id'] == employer_id:
            p['verification_status'] = 'pending'

