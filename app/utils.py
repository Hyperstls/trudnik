"""Утилиты: HTTP-запросы к PostgREST, вычисления, уведомления, rate limiting."""
import inspect
import json
import jwt as pyjwt
import logging
import math
import os
import re
import time
import uuid
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import requests as _requests
from flask import current_app, flash, jsonify, redirect, request, session, url_for

from app.config import Config

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])

# ═══════════════════════════════════════════════════════════════
# Circuit Breaker (этап 4.1)
# ═══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """Circuit Breaker для внешних HTTP-вызовов (PostgREST).

    Три состояния:
    - CLOSED: нормальная работа, запросы проходят
    - OPEN: цепь разомкнута, запросы не выполняются (таймаут 30 сек)
    - HALF_OPEN: пробный запрос для проверки восстановления

    Порог: 5 последовательных ошибок → OPEN → через 30 сек → HALF_OPEN.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = 'CLOSED'  # CLOSED | OPEN | HALF_OPEN
        self._lock = Lock()

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Выполнить вызов через circuit breaker.

        Args:
            func: функция-запрос.
            *args, **kwargs: аргументы для func.

        Returns:
            Результат вызова func или фейловый ответ при разомкнутой цепи.
        """
        # В режиме mock-тестирования отключаем circuit breaker — ошибки накапливаются
        # между запусками pytest и ломают последующие тесты.
        # Используем _is_mock_enabled() для консистентности с остальной mock-логикой
        # (учитывает SUPABASE_MOCK_MODE, TESTING=True и .mock_supabase файл).
        if _is_mock_enabled():
            return func(*args, **kwargs)

        with self._lock:
            if self.state == 'OPEN':
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = 'HALF_OPEN'
                else:
                    return _circuit_open_response()

        try:
            result = func(*args, **kwargs)
        except Exception:
            with self._lock:
                self._record_failure()
            raise

        with self._lock:
            if isinstance(result, dict) and not result.get('ok', True):
                self._record_failure()
            elif isinstance(result, SupabaseResponse) and not result.ok:
                self._record_failure()
            else:
                self.failure_count = 0
                if self.state == 'HALF_OPEN':
                    self.state = 'CLOSED'

        return result

    def _record_failure(self) -> None:
        """Зафиксировать ошибку. При превышении порога — разомкнуть цепь."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            current_app.logger.warning(
                'Circuit Breaker OPEN after %d failures', self.failure_count
            )


def _circuit_open_response() -> 'SupabaseResponse':
    """Создать ответ-заглушку при разомкнутой цепи."""
    return SupabaseResponse(ok=False, status_code=503, text='Circuit breaker open')


_cb_postgrest = CircuitBreaker(failure_threshold=10, recovery_timeout=60.0)
_cb_admin = CircuitBreaker(failure_threshold=10, recovery_timeout=60.0)


# ═══════════════════════════════════════════════════════════════
# Connection Pooling (этап 4.2)
# ═══════════════════════════════════════════════════════════════

# Публичная сессия для обычных запросов
_session = _requests.Session()
_session.headers.update({
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
})

# Админ-сессия для service_role запросов (повторное использование TCP-соединений)
_admin_session = _requests.Session()
_admin_session.headers.update({
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
})


# ═══════════════════════════════════════════════════════════════
# Кэширование
# ═══════════════════════════════════════════════════════════════

def cache_for(seconds: int = 30) -> Callable[[F], F]:
    """Простой in-memory кэш для функций.

    Args:
        seconds: время жизни кэша в секундах.

    Returns:
        Декоратор, кэширующий результат функции.

    Используется для декорирования функций, результат которых можно кэшировать
    на заданное время.
    """
    cache_store: Dict[str, tuple] = {}

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (func.__name__, repr(args), repr(sorted(kwargs.items())))
            now = time.time()
            if key in cache_store:
                result, expiry = cache_store[key]
                if now < expiry:
                    return result
            result = func(*args, **kwargs)
            cache_store[key] = (result, now + seconds)
            return result
        return wrapper  # type: ignore[return-value]
    return decorator


POSTGREST_URL = Config.POSTGREST_URL
PGRST_JWT_SECRET = Config.PGRST_JWT_SECRET

# ═══════════════════════════════════════════════════════════════
# JWT-хелперы для PostgREST-аутентификации
# ═══════════════════════════════════════════════════════════════

def get_service_role_headers() -> Dict[str, str]:
    """Создать заголовки с JWT service_role для админских операций (обход RLS).

    Returns:
        Словарь с заголовками Authorization и Content-Type.
    """
    token = pyjwt.encode(
        {'role': 'service_role'},
        PGRST_JWT_SECRET,
        algorithm='HS256'
    )
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def get_user_headers(user_id: Optional[str] = None) -> Dict[str, str]:
    """Создать заголовки с JWT для аутентифицированного пользователя.

    Args:
        user_id: UUID пользователя (если None — берётся из сессии Flask).

    Returns:
        Словарь с заголовками Authorization и Content-Type.
    """
    if user_id is None:
        user_id = session.get('user_id', '')
    payload = {
        'role': 'authenticated',
        'user_id': str(user_id) if user_id else '',
        'exp': int(time.time()) + 3600,
        'iat': int(time.time()),
    }
    token = pyjwt.encode(payload, PGRST_JWT_SECRET, algorithm='HS256')
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


# ═══════════════════════════════════════════════════════════════
# Безопасность service_role (этап 5.1)
# ═══════════════════════════════════════════════════════════════

# Множество разрешённых контекстов для service_role вызовов.
# Вызовы из тестов и скриптов — допустимы (admin-утилиты).
# Вызовы из Jinja2-контекста (template globals/context processors) — допустимы,
#   но должны быть минимизированы (предпочитать postgrest_request с токеном пользователя).
# Вызовы из Celery-задач — допустимы (нет пользовательской сессии).
_ADMIN_ALLOWED_PREFIXES = frozenset({
    'app.blueprints',       # Flask route handlers (серверная сторона)
    'app.services',         # Сервисный слой (может вызываться из Celery)
    'app.tasks',            # Celery-задачи (нет сессии пользователя)
    'app.utils',            # Внутренние хелперы (update_rating и др.)
    'app',                  # app/__init__.py (контекстные процессоры)
    'scripts',              # Административные скрипты
    'tests',                # Тесты
    'archive',              # Архивные утилиты
})

_ADMIN_WARN_PREFIXES = frozenset({
    # Шаблоны Jinja2: если admin_request вызывается из шаблона — это ошибка архитектуры.
    # Код шаблонов не должен иметь доступа к service_role.
    'app.templates',
})


def _get_caller_info() -> str:
    """Получить информацию о вызывающем модуле для аудит-лога.

    Просматривает стек вызовов и находит первый фрейм вне app.utils.
    Используется только для логирования, не для принятия решений о безопасности.

    Returns:
        Строка вида 'module.function:line' или 'unknown'.
    """
    try:
        frame = inspect.currentframe()
        # Поднимаемся по стеку: пропускаем _get_caller_info, _assert_service_key,
        # postgrest_admin_request и _make_request
        skip_count = 0
        while frame is not None:
            module_name = frame.f_globals.get('__name__', '')
            if module_name and module_name != __name__:
                func_name = frame.f_code.co_name
                line_no = frame.f_lineno
                return f"{module_name}.{func_name}:{line_no}"
            frame = frame.f_back
            skip_count += 1
            if skip_count > 20:  # Защита от бесконечного цикла
                break
    except Exception:
        pass
    return 'unknown'


def _assert_service_key() -> None:
    """Проверить, что PGRST_JWT_SECRET установлен перед выполнением admin-запроса.

    Если ключ не задан, JWT-токен не может быть создан.
    """
    if not PGRST_JWT_SECRET:
        caller = _get_caller_info()
        logger.error(
            "SECURITY: postgrest_admin_request вызван без PGRST_JWT_SECRET! "
            "Вызывающий: %s. Запрос будет выполнен с пустым JWT-токеном.",
            caller
        )


# ═══════════════════════════════════════════════════════════════
# PostgrestResponse
# ═══════════════════════════════════════════════════════════════

class SupabaseResponse:
    """Типизированный ответ от PostgREST API."""

    def __init__(self, ok: bool = False, status_code: int = 0,
                 data: Any = None, text: str = '',
                 headers: Any = None) -> None:
        self.ok = ok
        self.status_code = status_code
        self._data = data
        self.text = text
        self.headers = headers if headers is not None else {}

    def json(self) -> Any:
        """Вернуть распарсенные данные. Приоритет: _data, затем парсинг text."""
        if self._data is not None:
            return self._data
        try:
            return json.loads(self.text)
        except (json.JSONDecodeError, TypeError):
            return None


PostgrestResponse = SupabaseResponse  # Новое имя, отражающее переход на PostgREST


# ═══════════════════════════════════════════════════════════════
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
_original_post = _requests.post
_original_get = _requests.get
_original_delete = _requests.delete
_original_patch = _requests.patch
_original_put = _requests.put

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
    _requests.post = _mock_post
    _requests.delete = _mock_delete
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
    _requests.post = _original_post
    _requests.get = _original_get
    _requests.delete = _original_delete
    _requests.patch = _original_patch
    _requests.put = _original_put


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

        return SupabaseResponse(ok=True, status_code=200, data=result, text=json.dumps(result))

    # POST — создаём запись
    elif method == 'POST':
        data = kwargs.get('json', {})
        new_record = dict(data)
        if 'id' not in new_record:
            new_record['id'] = _gen_uuid()
        records.append(new_record)
        return SupabaseResponse(ok=True, status_code=201, data=[new_record], text=json.dumps([new_record]))

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
        return SupabaseResponse(ok=True, status_code=200, data=updated, text=json.dumps(updated))

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
        return SupabaseResponse(ok=True, status_code=204, data=to_delete, text='')

    return SupabaseResponse(ok=False, status_code=405, text=f'Method {method} not supported in mock')


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

        return SupabaseResponse(ok=True, status_code=200, data={'success': True, 'status': new_status}, text=json.dumps({'success': True, 'status': new_status}))

    # apply_job_atomic — создаём отклик
    if function_name == 'apply_job_atomic':
        job_id = params.get('p_job_id', '')
        worker_id = params.get('p_worker_id', '')
        # Проверка дубликата
        for a in _test_db.get('applications', []):
            if a.get('job_id') == job_id and a.get('worker_id') == worker_id:
                return SupabaseResponse(ok=True, status_code=200, data={'success': False, 'code': 'duplicate', 'error': 'Вы уже откликались на это задание'}, text=json.dumps({'success': False, 'code': 'duplicate', 'error': 'Вы уже откликались на это задание'}))
        # Проверка мест
        for j in _test_db.get('jobs', []):
            if j.get('id') == job_id:
                if j.get('current_workers', 0) >= j.get('max_workers', 99):
                    return SupabaseResponse(ok=True, status_code=200, data={'success': False, 'code': 'no_slots', 'error': 'Нет свободных мест'}, text=json.dumps({'success': False, 'code': 'no_slots', 'error': 'Нет свободных мест'}))
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
        return SupabaseResponse(ok=True, status_code=200, data={'success': True, 'id': new_app['id'], 'employer_id': employer_id}, text=json.dumps({'success': True, 'id': new_app['id'], 'employer_id': employer_id}))

    # delete_job_cascade — удаление задания и связанных записей
    if function_name == 'delete_job_cascade':
        job_id = params.get('p_job_id', '')
        _test_db['jobs'] = [j for j in _test_db.get('jobs', []) if j.get('id') != job_id]
        _test_db['applications'] = [a for a in _test_db.get('applications', []) if a.get('job_id') != job_id]
        _test_db['messages'] = [m for m in _test_db.get('messages', []) if m.get('job_id') != job_id]
        return SupabaseResponse(ok=True, status_code=200, data={'success': True}, text=json.dumps({'success': True}))

    # delete_user_cascade — удаление пользователя и связанных записей
    if function_name == 'delete_user_cascade':
        user_id = params.get('p_user_id', '')
        _test_db['profiles'] = [p for p in _test_db.get('profiles', []) if p.get('id') != user_id]
        _test_db['jobs'] = [j for j in _test_db.get('jobs', []) if j.get('employer_id') != user_id]
        _test_db['applications'] = [a for a in _test_db.get('applications', []) if a.get('worker_id') != user_id]
        return SupabaseResponse(ok=True, status_code=200, data={'success': True}, text=json.dumps({'success': True}))

    # get_job_stats / get_user_stats / get_dashboard_stats — статистика
    if function_name in ('get_job_stats', 'get_user_stats', 'get_dashboard_stats'):
        return SupabaseResponse(ok=True, status_code=200, data={'total': 0, 'open': 0, 'completed': 0, 'cancelled': 0}, text=json.dumps({'total': 0, 'open': 0, 'completed': 0, 'cancelled': 0}))

    # get_completed_jobs_between — проверка совместных завершённых заданий
    if function_name == 'get_completed_jobs_between':
        return SupabaseResponse(ok=True, status_code=200, data=[], text=json.dumps([]))

    # nearby_jobs — геопоиск заданий в радиусе (возвращает список jobs)
    if function_name == 'nearby_jobs':
        return SupabaseResponse(ok=True, status_code=200, data=[], text=json.dumps([]))

    return SupabaseResponse(ok=False, status_code=404, text=f'RPC {function_name} not mocked')


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

# ═══════════════════════════════════════════════════════════════
# Гео-вычисления
# ═══════════════════════════════════════════════════════════════

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Вычислить расстояние (км) между двумя точками по формуле гаверсинусов."""
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ═══════════════════════════════════════════════════════════════
# Auth helpers
# ═══════════════════════════════════════════════════════════════

def refresh_access_token() -> bool:
    """Генерирует новый JWT для PostgREST. Больше не требует refresh_token от Supabase Auth.
    
    Достаточно наличия user_id в сессии для генерации свежего токена.
    """
    user_id = session.get('user_id')
    
    if not user_id:
        return False
    
    try:
        payload = {
            'role': 'authenticated',
            'user_id': str(user_id),
            'exp': int(time.time()) + 3600,  # 1 час
            'iat': int(time.time()),
        }
        token = pyjwt.encode(
            payload,
            PGRST_JWT_SECRET,
            algorithm='HS256'
        )
        session['access_token'] = token
        session.modified = True
        return True
    except Exception:
        session.clear()
        return False



# ═══════════════════════════════════════════════════════════════
# HTTP-запросы к PostgREST
# ═══════════════════════════════════════════════════════════════

def postgrest_request(method: str, endpoint: str, **kwargs: Any) -> SupabaseResponse:
    """Сделать HTTP-запрос к PostgREST API с пользовательским JWT-токеном.

    Автоматически обновляет access_token при 401. Использует CircuitBreaker.
    При TESTING=True использует in-memory mock.

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт (например, 'jobs?status=eq.open').
        **kwargs: дополнительные аргументы для requests (json, headers, etc.).

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
    """
    # Mock активен при TESTING=True или SUPABASE_MOCK_MODE (безопасная проверка)
    if _is_mock_enabled():
        return _test_mock_request(method, endpoint, **kwargs)
    extra_headers = kwargs.pop('headers', None)

    def _make_request() -> SupabaseResponse:
        headers = get_user_headers()
        if extra_headers:
            headers.update(extra_headers)
        url = f'{POSTGREST_URL}/{endpoint}'
        # Дифференцированный таймаут: чтение быстрое (15с), мутации с триггерами — дольше (60с)
        _timeout = 15 if method.upper() == 'GET' else 60
        resp = _session.request(method, url, headers=headers, timeout=_timeout, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text, headers=resp.headers)

    try:
        resp = _cb_postgrest.call(_make_request)
        if resp.status_code == 401 and session.get('refresh_token'):
            if refresh_access_token():
                resp = _cb_postgrest.call(_make_request)
        return resp
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST request error: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_request: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))


def postgrest_admin_request(method: str, endpoint: str, **kwargs: Any) -> SupabaseResponse:
    """Сделать запрос к PostgREST API с JWT service_role (обход RLS).

    Использует _admin_session для переиспользования TCP-соединений.
    Использует CircuitBreaker.

    БЕЗОПАСНОСТЬ:
    - Эта функция обходит Row Level Security (RLS) и должна использоваться
      только на серверной стороне (Flask-роуты, Celery-задачи, скрипты).
    - НИКОГДА не вызывайте её из шаблонов Jinja2 или кода, который может
      быть выполнен в контексте клиента.
    - Перед добавлением нового вызова supabase_admin_request проверьте:
      1. Можно ли использовать postgrest_request с токеном пользователя?
      2. Можно ли использовать postgrest_rpc с проверкой прав в БД?
      3. Действительно ли операция требует обхода RLS?
    - Все вызовы логируются на DEBUG-уровне для аудита.

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт.
        **kwargs: дополнительные аргументы для requests.

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
    """
    # Проверка безопасности: ключ service_role должен быть задан
    _assert_service_key()

    # Аудит-лог: кто и откуда делает привилегированный запрос
    caller = _get_caller_info()
    logger.debug(
        "ADMIN_REQUEST: %s %s from %s",
        method, endpoint.split('?')[0], caller
    )

    # Проверка: предупреждаем, если service_role вызывается из подозрительного контекста
    caller_module = caller.split('.')[0] if '.' in caller else caller
    if caller_module in _ADMIN_WARN_PREFIXES:
        logger.warning(
            "SECURITY: postgrest_admin_request вызван из подозрительного контекста: %s. "
            "Код шаблонов не должен иметь доступа к service_role.",
            caller
        )

    # Mock активен при TESTING=True или SUPABASE_MOCK_MODE (безопасная проверка)
    if _is_mock_enabled():
        return _test_mock_request(method, endpoint, **kwargs)
    extra_headers = kwargs.pop('headers', None)
    headers = get_service_role_headers()
    if extra_headers:
        headers.update(extra_headers)

    def _make_request() -> SupabaseResponse:
        url = f'{POSTGREST_URL}/{endpoint}'
        # Дифференцированный таймаут: чтение быстрое (15с), мутации с триггерами — дольше (60с)
        _timeout = 15 if method.upper() == 'GET' else 60
        resp = _admin_session.request(method, url, headers=headers, timeout=_timeout, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text, headers=resp.headers)

    try:
        return _cb_admin.call(_make_request)
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST admin request error: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_admin_request: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))


# ═══════════════════════════════════════════════════════════════
# Загрузка файлов
# ═══════════════════════════════════════════════════════════════

MAX_UPLOAD_SIZE = Config.MAX_PHOTO_SIZE_MB * 1024 * 1024  # 5 MB


def upload_to_storage(bucket: str, file_path: str, file_data: bytes,
                       content_type: str) -> Optional[str]:
    """Сохранить файл в локальное хранилище (Amvera-совместимое).
    
    Файлы сохраняются в UPLOAD_FOLDER/<bucket>/<file_path>.
    Возвращает относительный URL для доступа через /uploads/<bucket>/<file_path>.
    
    Args:
        bucket: имя бакета (напр. 'avatars', 'verification-docs').
        file_path: путь к файлу внутри бакета.
        file_data: бинарные данные файла.
        content_type: MIME-тип файла (не используется при локальном хранении).
        
    Returns:
        URL загруженного файла или None при ошибке.
    """
    import os as _os
    from flask import current_app
    
    if file_data and len(file_data) > MAX_UPLOAD_SIZE:
        current_app.logger.warning('Upload rejected: file too large (%d bytes)', len(file_data))
        return None
    
    upload_dir = _os.path.join(
        current_app.config.get('UPLOAD_FOLDER', 'uploads'), bucket
    )
    _os.makedirs(upload_dir, exist_ok=True)
    
    full_path = _os.path.join(upload_dir, file_path)
    try:
        with open(full_path, 'wb') as f:
            f.write(file_data)
        current_app.logger.info(
            'File saved: %s/%s (%d bytes)', bucket, file_path, len(file_data)
        )
        # Return relative URL with cache-busting timestamp
        return f'/uploads/{bucket}/{file_path}?t={int(time.time())}'
    except OSError as e:
        current_app.logger.error('File save error: %s', e)
        return None


# ═══════════════════════════════════════════════════════════════
# RPC-вызовы (этап 4.4)
# ═══════════════════════════════════════════════════════════════

def postgrest_rpc(function_name: str, params: dict, use_admin: bool = False) -> SupabaseResponse:
    """Вызвать хранимую процедуру через PostgREST RPC.

    При TESTING=True использует in-memory mock.

    Args:
        function_name: имя хранимой процедуры (например, 'accept_application').
        params: словарь параметров для процедуры.
        use_admin: если True — использовать service_role key.

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
    """
    # Mock активен при TESTING=True или SUPABASE_MOCK_MODE (безопасная проверка)
    if _is_mock_enabled():
        return _test_mock_rpc(function_name, params)
    url = f'{POSTGREST_URL}/rpc/{function_name}'
    if use_admin:
        headers = get_service_role_headers()
    else:
        headers = get_user_headers()

    def _make_request() -> SupabaseResponse:
        resp = _session.post(url, headers=headers, json=params, timeout=60)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text)

    try:
        cb = _cb_admin if use_admin else _cb_postgrest
        resp = cb.call(_make_request)
        if resp.status_code == 401 and not use_admin and session.get('refresh_token'):
            if refresh_access_token():
                resp = cb.call(_make_request)
        return resp
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST RPC error ({function_name}): {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_rpc ({function_name}): {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))


# ═══════════════════════════════════════════════════════════════
# Хелперы заданий
# ═══════════════════════════════════════════════════════════════

def copy_job(original_job: dict) -> dict:
    """Создать копию задания для дублирования / перепубликации.

    Args:
        original_job: исходный словарь задания.

    Returns:
        Новый словарь с полями для создания копии (status='open', is_paid=True).
    """
    return {
        'employer_id': original_job['employer_id'],
        'organization_name': original_job.get('organization_name', ''),
        'org_description': original_job.get('org_description', ''),
        'object_description': original_job.get('object_description', ''),
        'work_type': original_job.get('work_type', ''),
        'detailed_description': original_job.get('detailed_description', ''),
        'date_time': original_job.get('date_time', ''),
        'payment_amount': original_job.get('payment_amount', 0),
        'address': original_job.get('address', ''),
        'city': original_job.get('city', ''),
        'lat': original_job.get('lat', Config.DEFAULT_LAT),
        'lng': original_job.get('lng', Config.DEFAULT_LNG),
        'status': 'open',
        'max_workers': original_job.get('max_workers', 1),
        'current_workers': 0,
    }


def update_rating(user_id: str, new_rating: float) -> None:
    """Обновить средний рейтинг пользователя.

    Args:
        user_id: UUID пользователя.
        new_rating: новый рейтинг (один отзыв).

    Использует admin_request для обхода RLS (вызывается от лица rat'ера, не владельца профиля).
    """
    ratings_resp = postgrest_admin_request('GET', f'ratings?rated_user_id=eq.{user_id}&select=rating')
    if not ratings_resp.ok or not ratings_resp.json():
        return

    ratings_list = ratings_resp.json()
    total = sum(r['rating'] for r in ratings_list)
    avg = round(total / len(ratings_list), 1)

    postgrest_admin_request('PATCH', f'profiles?id=eq.{user_id}', json={'rating': avg})


# ═══════════════════════════════════════════════════════════════
# Rate Limiting (in-memory, per-IP)
# ═══════════════════════════════════════════════════════════════

_rate_limits: Dict[str, List[float]] = defaultdict(list)
_RATE_WINDOW = Config.RATE_LIMIT_WINDOW      # секунд
_RATE_MAX_REQUESTS = Config.RATE_LIMIT_MAX    # запросов в окне


def rate_limit(f: F) -> F:
    """Декоратор: ограничение частоты POST-запросов по IP.

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


# ═══════════════════════════════════════════════════════════════
# Санитизация PostgREST (этап 3.1)
# ═══════════════════════════════════════════════════════════════

# Whitelist: разрешённые символы для PostgREST-параметров
# NOTE: .,* оставлены — экранируются бэкслешем в sanitize_postgrest()
# NOTE: ,:;'&()"<> удалены — обрабатываются шагами удаления/экранирования
_ALLOWED_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789'
    'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'
    ' -_./:*!?@#[]{}|+=\\`~%^$'
)

# Предкомпилированный pattern для удаления HTML-тегов (XSS-векторы)
_HTML_TAG_RE = re.compile(r'</?(script|style|iframe|svg)\b[^>]*>', re.IGNORECASE)


def sanitize_postgrest(value: Any) -> Any:
    """Экранировать спецсимволы PostgREST в пользовательском вводе.

    Этапы:
    1. URL-декодирование (%20 → пробел, %27 → ' и т.д.)
    2. Удаление HTML-тегов <script>, <style>, <iframe>, <svg> (XSS-векторы)
    3. Удаление опасных символов: ( ) , ; " ' & < >
    4. Экранирование спецсимволов PostgREST: . → \\. , * → \\*
    5. Whitelist-проверка: только разрешённые символы
    6. Обрезка пробелов

    Args:
        value: строка (или не-строка — возвращается как есть).

    Returns:
        Очищенная строка, безопасная для использования в PostgREST-запросах.
    """
    if not isinstance(value, str):
        return value

    # 1. URL-декодирование
    try:
        value = urllib.parse.unquote(value)
    except Exception:
        pass

    # 2. Удаляем HTML-теги (XSS-векторы: <script>, <style>, <iframe>, <svg>)
    value = _HTML_TAG_RE.sub('', value)

    # 3. Удаляем опасные символы, которые могут изменить структуру запроса
    for ch in '(),;"\'&<>':
        value = value.replace(ch, '')

    # 4. Экранируем спецсимволы PostgREST (точка и звёздочка — через backslash)
    value = value.replace('.', '\\.').replace('*', '\\*')

    # 5. Whitelist-проверка: удаляем все символы не из разрешённого набора
    value = ''.join(ch for ch in value if ch in _ALLOWED_CHARS)

    return value.strip()


# ═══════════════════════════════════════════════════════════════
# Проверка окна отзыва
# ═══════════════════════════════════════════════════════════════

def check_withdraw_window(job_date_time: Optional[str]) -> bool:
    """Проверить, можно ли отозвать отклик (не позднее 12 часов до начала задания).

    Args:
        job_date_time: ISO-формат даты/времени задания (строка).

    Returns:
        True если до начала более 12 часов и отзыв разрешён, иначе False.
    """
    if not job_date_time:
        return True
    try:
        job_dt = datetime.fromisoformat(job_date_time.replace('Z', '+00:00'))
        return (job_dt - datetime.now(timezone.utc)).total_seconds() > 12 * 3600
    except (ValueError, TypeError):
        return True


# ═══════════════════════════════════════════════════════════════
# Короткие хелперы
# ═══════════════════════════════════════════════════════════════

def uid() -> Optional[str]:
    """Короткий доступ к ID текущего пользователя из сессии.

    Returns:
        user_id или None.
    """
    return session.get('user_id')


def my_query(table: str, field: str = 'user_id', extra: str = '') -> str:
    """Построить PostgREST-запрос для текущего пользователя.

    Args:
        table: имя таблицы.
        field: имя поля для фильтрации по uid.
        extra: дополнительные параметры запроса (например, '&status=eq.open').

    Returns:
        Строка запроса вида 'notifications?user_id=eq.{uid}'.

    Examples:
        my_query('notifications') -> 'notifications?user_id=eq.{uid}'
        my_query('jobs', 'employer_id', '&status=eq.open') -> 'jobs?employer_id=eq.{uid}&status=eq.open'
    """
    u = uid()
    q = f'{table}?{field}=eq.{u}'
    if extra:
        q += extra
    return q


# ═══════════════════════════════════════════════════════════════
# Форматирование дат
# ═══════════════════════════════════════════════════════════════

# Русские названия месяцев (родительный падеж)
_MONTHS_RU = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
]

# Московский часовой пояс (UTC+3)
_MSK_TZ = timezone(timedelta(hours=3))


def format_datetime(iso_string: Optional[str]) -> str:
    """Преобразовать ISO-строку даты в человеко-читаемый формат на русском.

    Поддерживаемые форматы:
      - '2026-06-16T00:47'       → '16 июня 2026, 00:47'
      - '2026-06-16T00:47:00'    → '16 июня 2026, 00:47'
      - '2026-06-16T00:47:00+00:00' → с учётом временной зоны
      - '2026-06-16'             → '16 июня 2026'
      - Сегодняшняя дата         → 'Сегодня, 14:30'
      - Вчерашняя дата           → 'Вчера, 09:15'

    Все даты без временной зоны считаются UTC и конвертируются в MSK (UTC+3).

    Args:
        iso_string: ISO-формат даты/времени или None/пустая строка.

    Returns:
        Отформатированная строка или '—' при невалидном вводе.
    """
    if not iso_string:
        return '—'

    try:
        dt = None
        # Пробуем распространённые форматы
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
            try:
                dt = datetime.strptime(iso_string[:len(fmt)], fmt)
                break
            except (ValueError, IndexError):
                continue

        if dt is None:
            # Пробуем fromisoformat (Python 3.7+) — обрабатывает timezone offset
            try:
                dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return '—'

        # Если время без tzinfo — считаем UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Конвертируем в московское время
        dt_msk = dt.astimezone(_MSK_TZ)

        # Текущее московское время для сравнения «сегодня/вчера»
        now_msk = datetime.now(timezone.utc).astimezone(_MSK_TZ)

        # Если без времени (только дата) — просто форматируем дату
        has_time = 'T' in str(iso_string) and len(iso_string) > 10

        # «Сегодня» / «Вчера» только если есть время
        if has_time:
            if dt_msk.date() == now_msk.date():
                return f"Сегодня, {dt_msk.strftime('%H:%M')}"
            if dt_msk.date() == (now_msk - timedelta(days=1)).date():
                return f"Вчера, {dt_msk.strftime('%H:%M')}"

        # Полный формат: «16 июня 2026, 00:47»
        month_name = _MONTHS_RU[dt_msk.month - 1]
        if has_time:
            return f"{dt_msk.day} {month_name} {dt_msk.year}, {dt_msk.strftime('%H:%M')}"
        else:
            return f"{dt_msk.day} {month_name} {dt_msk.year}"

    except Exception:
        return '—'


# ═══════════════════════════════════════════════════════════════
# VAPID-ключи для Web Push API
# ═══════════════════════════════════════════════════════════════

def generate_vapid_keys():
    """Генерирует VAPID-ключи для Web Push. Вызывается из CLI.

    Использует криптографию на эллиптических кривых (P-256 / SECP256R1).
    Возвращает пару ключей в base64url-кодировке без padding.

    Returns:
        Кортеж (private_key, public_key) — строки в base64url.

    Пример использования:
        python -c "from app.utils import generate_vapid_keys; print(generate_vapid_keys())"
    """
    import base64 as _base64

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        raise ImportError(
            'cryptography не установлен. Установите: pip install cryptography'
        )

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Экспорт в raw-формат
    private_raw = private_key.private_numbers().private_value.to_bytes(32, 'big')

    pub_numbers = public_key.public_numbers()
    public_raw = (
        pub_numbers.x.to_bytes(32, 'big') +
        pub_numbers.y.to_bytes(32, 'big')
    )

    # Кодирование в base64url без padding
    private_b64 = _base64.urlsafe_b64encode(private_raw).rstrip(b'=').decode('ascii')
    public_b64 = _base64.urlsafe_b64encode(public_raw).rstrip(b'=').decode('ascii')

    return private_b64, public_b64


# ═══════════════════════════════════════════════════════════════
# Обратная совместимость: старые имена функций
# ═══════════════════════════════════════════════════════════════
supabase_request = postgrest_request
supabase_admin_request = postgrest_admin_request
supabase_rpc = postgrest_rpc
SUPABASE_URL = POSTGREST_URL
SUPABASE_KEY = None  # Больше не используется, оставлен для совместимости импортов
SERVICE_KEY = None   # Больше не используется, оставлен для совместимости импортов
