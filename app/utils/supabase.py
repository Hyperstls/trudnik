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
            try:
                current_app.logger.warning(
                    'Circuit Breaker OPEN after %d failures', self.failure_count
                )
            except Exception:
                pass


def _circuit_open_response() -> 'SupabaseResponse':
    """Создать ответ-заглушку при разомкнутой цепи."""
    resp = SupabaseResponse(ok=False, status_code=503, text='Circuit breaker open')
    resp.circuit_open = True
    return resp


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

def get_service_role_headers() -> Dict[str, str]:
    """Создать заголовки с JWT service_role для админских операций (обход RLS).

    Returns:
        Словарь с заголовками Authorization и Content-Type.
    """
    token = pyjwt.encode(
        {
            'role': 'service_role',
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

    Args:
        user_id: UUID пользователя (если None — берётся из сессии Flask).

    Returns:
        Словарь с заголовками Authorization и Content-Type.
    """
    if user_id is None:
        user_id = session.get('user_id', '')
    # Если пользователь не аутентифицирован — используем роль anon
    role = session.get('role', 'authenticated') if user_id else 'anon'
    payload = {
        'role': role,
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
# PostgrestResponse / SupabaseResponse
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
        self.circuit_open = False

    def json(self) -> Any:
        """Вернуть распарсенные данные. Приоритет: _data, затем парсинг text."""
        if self._data is not None:
            return self._data
        try:
            return json.loads(self.text)
        except (json.JSONDecodeError, TypeError):
            return None


PostgrestResponse = SupabaseResponse


# ═══════════════════════════════════════════════════════════════
# Auth helpers
# ═══════════════════════════════════════════════════════════════

def refresh_access_token() -> bool:
    """Генерирует новый JWT для PostgREST из user_id в сессии."""
    user_id = session.get('user_id')

    if not user_id:
        return False

    try:
        role = session.get('role', 'authenticated')
        payload = {
            'role': role,
            'user_id': str(user_id),
            'exp': int(time.time()) + 3600,
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
    if _is_mock_enabled():
        return _test_mock_request(method, endpoint, **kwargs)
    extra_headers = kwargs.pop('headers', None)

    def _make_request() -> SupabaseResponse:
        headers = get_user_headers()
        if extra_headers:
            headers.update(extra_headers)
        url = f'{POSTGREST_URL}/{endpoint}'
        _timeout = 15 if method.upper() == 'GET' else 10
        resp = _session.request(method, url, headers=headers, timeout=_timeout, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text,
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

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт.
        **kwargs: дополнительные аргументы для requests.

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
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
    if extra_headers:
        headers.update(extra_headers)

    def _make_request() -> SupabaseResponse:
        url = f'{POSTGREST_URL}/{endpoint}'
        _timeout = 15 if method.upper() == 'GET' else 10
        resp = _admin_session.request(method, url, headers=headers, timeout=_timeout, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text,
                                headers=resp.headers)

    try:
        return _cb_admin.call(_make_request)
    except _requests.RequestException as e:
        current_app.logger.error(f"PostgREST admin request error: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in postgrest_admin_request: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))


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
    if _is_mock_enabled():
        return _test_mock_rpc(function_name, params)
    url = f'{POSTGREST_URL}/rpc/{function_name}'
    if use_admin:
        headers = get_service_role_headers()
    else:
        headers = get_user_headers()

    def _make_request() -> SupabaseResponse:
        resp = _session.post(url, headers=headers, json=params, timeout=10)
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
        content_type: MIME-тип файла.

    Returns:
        URL загруженного файла или None при ошибке.
    """
    import os as _os

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
        return f'/uploads/{bucket}/{file_path}?t={int(time.time())}'
    except OSError as e:
        current_app.logger.error('File save error: %s', e)
        return None


# ═══════════════════════════════════════════════════════════════
# VAPID-ключи для Web Push API
# ═══════════════════════════════════════════════════════════════

def generate_vapid_keys():
    """Генерирует VAPID-ключи для Web Push. Вызывается из CLI."""
    import base64 as _base64

    try:
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        raise ImportError(
            'cryptography не установлен. Установите: pip install cryptography'
        )

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    private_raw = private_key.private_numbers().private_value.to_bytes(32, 'big')

    pub_numbers = public_key.public_numbers()
    public_raw = (
        pub_numbers.x.to_bytes(32, 'big') +
        pub_numbers.y.to_bytes(32, 'big')
    )

    private_b64 = _base64.urlsafe_b64encode(private_raw).rstrip(b'=').decode('ascii')
    public_b64 = _base64.urlsafe_b64encode(public_raw).rstrip(b'=').decode('ascii')

    return private_b64, public_b64


# ═══════════════════════════════════════════════════════════════
# Алиасы для обратной совместимости
# ═══════════════════════════════════════════════════════════════

supabase_request = postgrest_request
supabase_admin_request = postgrest_admin_request
supabase_rpc = postgrest_rpc

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
