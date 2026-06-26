"""Supabase/PostgREST-клиент: HTTP-запросы, JWT-заголовки, Circuit Breaker, connection pooling."""

import inspect
import json
import logging
import os
import secrets
import time
from threading import Lock
from typing import Any, Callable, Dict, Optional, TypeVar

import jwt as pyjwt
import requests as _requests
from flask import current_app, session

# Публичный алиас для тестов
requests = _requests

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
    - OPEN: цепь разомкнута, запросы не выполняются (таймаут recovery_timeout сек)
    - HALF_OPEN: пробный запрос для проверки восстановления

    Порог: failure_threshold последовательных ошибок → OPEN →
    через recovery_timeout сек → HALF_OPEN.

    Особенности:
    - 403 (permission denied) НЕ размыкает цепь — это проблема прав, а не доступности
    - При OPEN состоянии выполняется health-check напрямую (в обход CB)
      для быстрого восстановления, если сервис снова стал доступен
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = 'CLOSED'  # CLOSED | OPEN | HALF_OPEN
        self._lock = Lock()

    def _check_postgrest_health(self) -> bool:
        """Проверить доступность PostgREST через health endpoint (в обход CB).

        Выполняет прямой GET-запрос к /health.html PostgREST с коротким таймаутом.
        Этот метод используется, когда CB находится в состоянии OPEN,
        чтобы быстро определить, восстановился ли сервис.

        Returns:
            True, если PostgREST отвечает 200/204/404 (жив), иначе False.
        """
        try:
            import requests as _req
            postgrest_url = POSTGREST_URL.strip()
            # /health.html возвращает 200 если PostgREST жив
            r = _req.get(f'{postgrest_url}/health.html', timeout=5)
            return r.status_code in (200, 204, 404)
        except Exception:
            return False

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Выполнить вызов через circuit breaker.

        Args:
            func: функция-запрос.
            *args, **kwargs: аргументы для func.

        Returns:
            Результат вызова func или фейловый ответ при разомкнутой цепи.
        """
        if _is_mock_enabled():
            return func(*args, **kwargs)

        with self._lock:
            if self.state == 'OPEN':
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = 'HALF_OPEN'
                else:
                    # Пробуем health-check напрямую (в обход CB)
                    if self._check_postgrest_health():
                        # Сервис снова доступен — сбрасываем CB
                        logger.info(
                            'Circuit Breaker: PostgREST health check OK, '
                            'resetting from OPEN to CLOSED'
                        )
                        self.reset()
                    else:
                        return _circuit_open_response()

        try:
            result = func(*args, **kwargs)
        except Exception:
            with self._lock:
                self._record_failure(exception=True)
            raise

        with self._lock:
            if isinstance(result, PostgrestResponse) and not result.ok:
                # 403 (permission denied) — не проблема доступности,
                # не размыкаем цепь (проблема прав, а не сервиса)
                if result.status_code == 403:
                    logger.warning(
                        'Circuit Breaker: 403 Forbidden (permission denied) '
                        '— NOT recording as failure'
                    )
                else:
                    self._record_failure(status_code=result.status_code)
            elif isinstance(result, dict) and not result.get('ok', True):
                self._record_failure()
            else:
                self.failure_count = 0
                if self.state == 'HALF_OPEN':
                    self.state = 'CLOSED'

        return result

    def _record_failure(self, status_code: int = 0, exception: bool = False) -> None:
        """Зафиксировать ошибку. При превышении порога — разомкнуть цепь.

        Args:
            status_code: HTTP-статус код ответа (0 если неизвестен).
            exception: True если ошибка вызвана исключением, а не HTTP-ответом.
        """
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = 'OPEN'
            try:
                extra = ''
                if status_code:
                    extra = f' (status={status_code})'
                elif exception:
                    extra = ' (exception)'
                current_app.logger.warning(
                    'Circuit Breaker OPEN after %d failures%s',
                    self.failure_count, extra
                )
            except Exception:
                pass

    def reset(self) -> None:
        """Сбросить Circuit Breaker в исходное состояние (CLOSED, failures=0)."""
        with self._lock:
            self.failure_count = 0
            self.last_failure_time = 0.0
            self.state = 'CLOSED'


def _circuit_open_response() -> 'PostgrestResponse':
    """Создать ответ-заглушку при разомкнутой цепи.

    Возвращает HTTP 503 (Service Unavailable) с понятным сообщением.
    Вызывающий код может проверить ``resp.circuit_open`` и/или
    ``is_circuit_open(resp)`` для принятия решения.

    Returns:
        PostgrestResponse со статусом 503 и circuit_open=True.
    """
    resp = PostgrestResponse(
        ok=False,
        status_code=503,
        text=(
            'PostgREST service unavailable (circuit breaker open). '
            'The service is temporarily down. Please try again later.'
        ),
    )
    resp.circuit_open = True
    return resp


def is_circuit_open(resp: Any) -> bool:
    """Проверить, является ли ответ результатом разомкнутой цепи Circuit Breaker.

    Удобная обёртка над ``hasattr(resp, 'circuit_open') and resp.circuit_open``.
    Используйте во всех view-функциях вместо прямой проверки атрибута.

    Args:
        resp: PostgrestResponse или любой объект с атрибутом circuit_open.

    Returns:
        True если цепь разомкнута, иначе False.
    """
    return hasattr(resp, 'circuit_open') and bool(resp.circuit_open)


_cb_postgrest = CircuitBreaker(
    failure_threshold=Config.CB_FAILURE_THRESHOLD,
    recovery_timeout=Config.CB_RECOVERY_TIMEOUT
)
_cb_admin = CircuitBreaker(
    failure_threshold=Config.CB_FAILURE_THRESHOLD,
    recovery_timeout=Config.CB_RECOVERY_TIMEOUT
)


def get_circuit_breaker_state():
    """Возвращает состояние обоих Circuit Breaker для мониторинга."""
    return {
        'postgrest': {
            'state': _cb_postgrest.state,
            'failure_count': _cb_postgrest.failure_count,
            'failure_threshold': _cb_postgrest.failure_threshold,
            'recovery_timeout': _cb_postgrest.recovery_timeout,
            'last_failure_time': _cb_postgrest.last_failure_time,
        },
        'admin': {
            'state': _cb_admin.state,
            'failure_count': _cb_admin.failure_count,
            'failure_threshold': _cb_admin.failure_threshold,
            'recovery_timeout': _cb_admin.recovery_timeout,
            'last_failure_time': _cb_admin.last_failure_time,
        }
    }


# ═══════════════════════════════════════════════════════════════
# Connection Pooling (этап 4.2)
# ═══════════════════════════════════════════════════════════════

_session = _requests.Session()
_session.headers.update({
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
})

_admin_session = _requests.Session()
_admin_session.headers.update({
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
})


# ═══════════════════════════════════════════════════════════════
# Кэширование (in-memory)
# ═══════════════════════════════════════════════════════════════

def cache_for(seconds: int = 30) -> Callable[[F], F]:
    """Простой in-memory кэш для функций.

    Args:
        seconds: время жизни кэша в секундах.

    Returns:
        Декоратор, кэширующий результат функции.
    """
    cache_store: Dict[str, tuple] = {}

    def decorator(func: F) -> F:
        from functools import wraps as _wraps

        @_wraps(func)
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

# Роль, под которой PostgREST подключается к PostgreSQL.
# Используется как fallback, когда настоящий service_role недоступен.
# PostgREST подключен к БД как trudnikapp, и SET ROLE trudnikapp
# является no-op (всегда работает). Роли service_role/anon/authenticated
# не могут быть назначены без SUPERUSER доступа.
_PGRST_DB_ROLE = 'trudnikapp'


def get_service_role_headers() -> Dict[str, str]:
    """Создать заголовки с JWT для админских операций (обход RLS).

    ВАЖНО: На продакшене (Amvera) нет SUPERUSER-доступа к PostgreSQL,
    поэтому невозможно выполнить GRANT service_role TO trudnikapp.
    Вместо этого используется роль trudnikapp — текущий пользователь БД,
    под которым PostgREST подключается. SET ROLE trudnikapp — no-op.

    Returns:
        Словарь с заголовками Authorization и Content-Type.
    """
    token = pyjwt.encode(
        {
            'role': _PGRST_DB_ROLE,
            'exp': int(time.time()) + 300,  # 5 минут
            'iat': int(time.time()),
            'jti': secrets.token_hex(8),
        },
        PGRST_JWT_SECRET,
        algorithm='HS256'
    )
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


def get_user_headers(user_id: Optional[str] = None) -> Dict[str, str]:
    """Создать заголовки с JWT для аутентифицированного пользователя.

    ВАЖНО: На продакшене (Amvera) нет SUPERUSER-доступа к PostgreSQL,
    поэтому невозможно SET ROLE authenticated/anon. Используется роль
    trudnikapp — текущий пользователь БД PostgREST.

    Args:
        user_id: UUID пользователя (если None — берётся из сессии Flask).

    Returns:
        Словарь с заголовками Authorization и Content-Type.
    """
    from app.utils.auth import generate_jwt
    if user_id is None:
        user_id = session.get('user_id', '')
    # Всегда используем trudnikapp (текущий пользователь PostgREST),
    # т.к. SET ROLE authenticated/anon требует SUPERUSER
    role = _PGRST_DB_ROLE
    token = generate_jwt(str(user_id) if user_id else '', role)
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }


# ═══════════════════════════════════════════════════════════════
# Безопасность service_role (этап 5.1)
# ═══════════════════════════════════════════════════════════════

_ADMIN_ALLOWED_PREFIXES = frozenset({
    'app.blueprints',
    'app.services',
    'app.tasks',
    'app.utils',
    'app',
    'scripts',
    'tests',
    'archive',
})

_ADMIN_WARN_PREFIXES = frozenset({
    'app.templates',
})


def _get_caller_info() -> str:
    """Получить информацию о вызывающем модуле для аудит-лога."""
    try:
        frame = inspect.currentframe()
        skip_count = 0
        while frame is not None:
            module_name = frame.f_globals.get('__name__', '')
            if module_name and module_name != __name__:
                func_name = frame.f_code.co_name
                line_no = frame.f_lineno
                return f"{module_name}.{func_name}:{line_no}"
            frame = frame.f_back
            skip_count += 1
            if skip_count > 20:
                break
    except Exception:
        pass
    return 'unknown'


def _assert_service_key() -> None:
    """Проверить, что PGRST_JWT_SECRET установлен перед выполнением admin-запроса."""
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

class PostgrestResponse:
    """Типизированный ответ от PostgREST API."""

    def __init__(self, ok: bool = False, status_code: int = 0,
                 data: Any = None, text: str = '',
                 headers: Any = None) -> None:
        self.ok = ok
        self.status_code = status_code
        self._data = data
        self.text = text
        self.headers = headers if headers is not None else {}
        self.circuit_open = False

    def json(self) -> Any:
        """Вернуть распарсенные данные. Приоритет: _data, затем парсинг text."""
        if self._data is not None:
            return self._data
        try:
            return json.loads(self.text)
        except (json.JSONDecodeError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════
# Auth helpers
# ═══════════════════════════════════════════════════════════════

def refresh_access_token() -> bool:
    """Генерирует новый JWT для PostgREST из user_id в сессии (делегирует в app.utils.auth)."""
    from app.utils.auth import refresh_access_token as _refresh
    return _refresh()


# ═══════════════════════════════════════════════════════════════
# HTTP-запросы к PostgREST
# ═══════════════════════════════════════════════════════════════

def postgrest_request(method: str, endpoint: str, **kwargs: Any) -> PostgrestResponse:
    """Сделать HTTP-запрос к PostgREST API с пользовательским JWT-токеном.

    Автоматически обновляет access_token при 401. Использует CircuitBreaker.
    При TESTING=True использует in-memory mock.

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт (например, 'jobs?status=eq.open').
        **kwargs: дополнительные аргументы для requests (json, headers, etc.).

    Returns:
        PostgrestResponse с полями ok, status_code, json(), text.
    """
    if _is_mock_enabled():
        return _test_mock_request(method, endpoint, **kwargs)
    extra_headers = kwargs.pop('headers', None)

    def _make_request() -> PostgrestResponse:
        headers = get_user_headers()
        if extra_headers:
            headers.update(extra_headers)
        url = f'{POSTGREST_URL.strip()}/{endpoint}'
        _timeout = 15 if method.upper() == 'GET' else 10
        resp = _session.request(method, url, headers=headers, timeout=_timeout, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return PostgrestResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text,
                                headers=resp.headers)

    try:
        resp = _cb_postgrest.call(_make_request)
        if resp.status_code == 401 and session.get('refresh_token'):
            if refresh_access_token():
                time.sleep(0.5)  # небольшая задержка перед повтором
                resp = _cb_postgrest.call(_make_request)
        return resp
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST request error: {e}")
        return PostgrestResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_request: {e}")
        return PostgrestResponse(ok=False, status_code=0, text=str(e))


def postgrest_admin_request(method: str, endpoint: str, **kwargs: Any) -> PostgrestResponse:
    """Сделать запрос к PostgREST API с JWT service_role (обход RLS).

    Использует _admin_session для переиспользования TCP-соединений.
    Использует CircuitBreaker.

    БЕЗОПАСНОСТЬ:
    - Эта функция обходит Row Level Security (RLS) и должна использоваться
      только на серверной стороне (Flask-роуты, Celery-задачи, скрипты).
    - НИКОГДА не вызывайте её из шаблонов Jinja2 или кода, который может
      быть выполнен в контексте клиента.

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт.
        **kwargs: дополнительные аргументы для requests.

    Returns:
        PostgrestResponse с полями ok, status_code, json(), text.
    """
    _assert_service_key()

    caller = _get_caller_info()
    logger.debug(
        "ADMIN_REQUEST: %s %s from %s",
        method, endpoint.split('?')[0], caller
    )

    caller_module = caller.split('.')[0] if '.' in caller else caller
    if caller_module in _ADMIN_WARN_PREFIXES:
        logger.warning(
            "SECURITY: postgrest_admin_request вызван из подозрительного контекста: %s. "
            "Код шаблонов не должен иметь доступа к service_role.",
            caller
        )

    if _is_mock_enabled():
        return _test_mock_request(method, endpoint, **kwargs)
    extra_headers = kwargs.pop('headers', None)
    headers = get_service_role_headers()
    # Для form-data (RPC вызовы) переопределяем Content-Type,
    # т.к. сессия _admin_session имеет Content-Type: application/json по умолчанию
    if 'data' in kwargs:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if extra_headers:
        headers.update(extra_headers)

    def _make_request() -> PostgrestResponse:
        url = f'{POSTGREST_URL.strip()}/{endpoint}'
        _timeout = 15 if method.upper() == 'GET' else 10
        resp = _admin_session.request(method, url, headers=headers, timeout=_timeout, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return PostgrestResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text,
                                headers=resp.headers)

    try:
        return _cb_admin.call(_make_request)
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST admin request error: {e}")
        return PostgrestResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_admin_request: {e}")
        return PostgrestResponse(ok=False, status_code=0, text=str(e))


# ═══════════════════════════════════════════════════════════════
# RPC-вызовы (этап 4.4)
# ═══════════════════════════════════════════════════════════════

def postgrest_rpc(function_name: str, params: dict, use_admin: bool = False) -> PostgrestResponse:
    """Вызвать хранимую процедуру через PostgREST RPC.

    При TESTING=True использует in-memory mock.

    Args:
        function_name: имя хранимой процедуры (например, 'accept_application').
        params: словарь параметров для процедуры.
        use_admin: если True — использовать service_role key.

    Returns:
        PostgrestResponse с полями ok, status_code, json(), text.
    """
    if _is_mock_enabled():
        return _test_mock_rpc(function_name, params)
    url = f'{POSTGREST_URL.strip()}/rpc/{function_name}'
    if use_admin:
        headers = get_service_role_headers()
    else:
        headers = get_user_headers()

    def _make_request() -> PostgrestResponse:
        resp = _session.post(url, headers=headers, json=params, timeout=10)
        try:
            data = resp.json()
        except Exception:
            data = None
        return PostgrestResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text)

    try:
        cb = _cb_admin if use_admin else _cb_postgrest
        resp = cb.call(_make_request)
        if resp.status_code == 401 and not use_admin and session.get('refresh_token'):
            if refresh_access_token():
                resp = cb.call(_make_request)
        return resp
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST RPC error ({function_name}): {e}")
        return PostgrestResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_rpc ({function_name}): {e}")
        return PostgrestResponse(ok=False, status_code=0, text=str(e))


# ═══════════════════════════════════════════════════════════════
# Загрузка файлов
# ═══════════════════════════════════════════════════════════════

MAX_UPLOAD_SIZE = Config.MAX_PHOTO_SIZE_MB * 1024 * 1024  # 5 MB


# ═══════════════════════════════════════════════════════════════
# Mock imports (ленивые, разрешаются при инициализации пакета)
# ═══════════════════════════════════════════════════════════════

# Эти импорты будут разрешены через __init__.py пакета
# Здесь они объявлены как ссылки, которые заполняются при инициализации
_test_db = None
_uuid_counter = None
_gen_uuid = None
_test_auth_tokens = None
_MockRequestsResponse = None
_should_intercept = None
_mock_post = None
_mock_delete = None
_install_auth_mock = None
_uninstall_auth_mock = None
_is_mock_enabled = lambda: False
_test_mock_request = None
_test_mock_rpc = None
_reset_test_db = None
_seed_test_db = None
