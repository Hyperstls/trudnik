"""Утилиты: HTTP-запросы к Supabase, вычисления, уведомления, rate limiting."""
import json
import math
import time
import uuid
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union

import requests as _requests
from flask import current_app, flash, jsonify, redirect, request, session, url_for

from app.config import Config

F = TypeVar('F', bound=Callable[..., Any])

# ═══════════════════════════════════════════════════════════════
# Circuit Breaker (этап 4.1)
# ═══════════════════════════════════════════════════════════════

class CircuitBreaker:
    """Circuit Breaker для внешних HTTP-вызовов (Supabase).

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


_cb_supabase = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
_cb_admin = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)


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


SUPABASE_URL = Config.SUPABASE_URL
SUPABASE_KEY = Config.SUPABASE_ANON_KEY
SERVICE_KEY = Config.SUPABASE_SERVICE_ROLE_KEY


# ═══════════════════════════════════════════════════════════════
# SupabaseResponse
# ═══════════════════════════════════════════════════════════════

class SupabaseResponse:
    """Типизированный ответ от Supabase REST API."""

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
    """Обновить access_token через refresh_token в сессии.

    Returns:
        True если обновление успешно, иначе False.
    """
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        return False
    url = f'{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token'
    try:
        resp = _requests.post(url, json={'refresh_token': refresh_token},
                              headers={'apikey': SUPABASE_KEY, 'Content-Type': 'application/json'},
                              timeout=10)
        if resp.ok:
            data = resp.json()
            session['access_token'] = data['access_token']
            session['refresh_token'] = data.get('refresh_token', refresh_token)
            session.modified = True
            return True
        else:
            session.clear()
            return False
    except _requests.RequestException:
        return False


# ═══════════════════════════════════════════════════════════════
# HTTP-запросы к Supabase
# ═══════════════════════════════════════════════════════════════

def supabase_request(method: str, endpoint: str, **kwargs: Any) -> SupabaseResponse:
    """Сделать HTTP-запрос к Supabase REST API с пользовательским токеном.

    Автоматически обновляет access_token при 401. Использует CircuitBreaker.

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт (например, 'jobs?status=eq.open').
        **kwargs: дополнительные аргументы для requests (json, headers, etc.).

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
    """
    extra_headers = kwargs.pop('headers', None)

    def _make_request() -> SupabaseResponse:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {session.get("access_token") or SUPABASE_KEY}',
        }
        if extra_headers:
            headers.update(extra_headers)
        url = f'{SUPABASE_URL}/rest/v1/{endpoint}'
        resp = _session.request(method, url, headers=headers, timeout=15, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text, headers=resp.headers)

    try:
        resp = _cb_supabase.call(_make_request)
        if resp.status_code == 401 and session.get('refresh_token'):
            if refresh_access_token():
                resp = _cb_supabase.call(_make_request)
        return resp
    except _requests.RequestException as e:
        current_app.logger.error(f"Supabase request error: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in supabase_request: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))


def supabase_admin_request(method: str, endpoint: str, **kwargs: Any) -> SupabaseResponse:
    """Сделать запрос к Supabase REST API с service_role_key (обход RLS).

    Использует _admin_session для переиспользования TCP-соединений.
    Использует CircuitBreaker.

    Args:
        method: HTTP-метод (GET, POST, PATCH, DELETE).
        endpoint: PostgREST-эндпоинт.
        **kwargs: дополнительные аргументы для requests.

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
    """
    extra_headers = kwargs.pop('headers', None)
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
    }
    if extra_headers:
        headers.update(extra_headers)

    def _make_request() -> SupabaseResponse:
        url = f'{SUPABASE_URL}/rest/v1/{endpoint}'
        resp = _admin_session.request(method, url, headers=headers, timeout=15, **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text, headers=resp.headers)

    try:
        return _cb_admin.call(_make_request)
    except _requests.RequestException as e:
        current_app.logger.error(f"Supabase admin request error: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in supabase_admin_request: {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))


# ═══════════════════════════════════════════════════════════════
# Загрузка файлов
# ═══════════════════════════════════════════════════════════════

MAX_UPLOAD_SIZE = Config.MAX_PHOTO_SIZE_MB * 1024 * 1024  # 5 MB


def upload_to_storage(bucket: str, file_path: str, file_data: bytes,
                       content_type: str) -> Optional[str]:
    """Загрузить файл в Supabase Storage.

    Args:
        bucket: имя бакета.
        file_path: путь к файлу в бакете.
        file_data: бинарные данные файла.
        content_type: MIME-тип файла.

    Returns:
        Публичный URL загруженного файла или None при ошибке.
    """
    if file_data and len(file_data) > MAX_UPLOAD_SIZE:
        current_app.logger.warning('Upload rejected: file too large (%d bytes)', len(file_data))
        return None
    url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {session["access_token"]}',
    }
    try:
        resp = _requests.post(url, headers=headers,
                              files={'file': (file_path, file_data, content_type)},
                              timeout=30)
        if resp.status_code in (200, 201):
            return f'{SUPABASE_URL}/storage/v1/object/public/{bucket}/{file_path}?t={int(time.time())}'
    except _requests.RequestException:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# RPC-вызовы (этап 4.4)
# ═══════════════════════════════════════════════════════════════

def supabase_rpc(function_name: str, params: dict, use_admin: bool = False) -> SupabaseResponse:
    """Вызвать хранимую процедуру Supabase через PostgREST RPC.

    Args:
        function_name: имя хранимой процедуры (например, 'accept_application').
        params: словарь параметров для процедуры.
        use_admin: если True — использовать service_role key.

    Returns:
        SupabaseResponse с полями ok, status_code, json(), text.
    """
    url = f'{SUPABASE_URL}/rest/v1/rpc/{function_name}'
    if use_admin:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
        }
    else:
        headers = {
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {session.get("access_token") or SUPABASE_KEY}',
            'Content-Type': 'application/json',
        }

    def _make_request() -> SupabaseResponse:
        resp = _session.post(url, headers=headers, json=params, timeout=15)
        try:
            data = resp.json()
        except Exception:
            data = None
        return SupabaseResponse(ok=resp.ok, status_code=resp.status_code, data=data, text=resp.text)

    try:
        cb = _cb_admin if use_admin else _cb_supabase
        resp = cb.call(_make_request)
        if resp.status_code == 401 and not use_admin and session.get('refresh_token'):
            if refresh_access_token():
                resp = cb.call(_make_request)
        return resp
    except _requests.RequestException as e:
        current_app.logger.error(f"Supabase RPC error ({function_name}): {e}")
        return SupabaseResponse(ok=False, status_code=0, text=str(e))
    except Exception as e:
        current_app.logger.error(f"Unexpected error in supabase_rpc ({function_name}): {e}")
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
        'is_paid': True,
    }


def update_rating(user_id: str, new_rating: float) -> None:
    """Обновить средний рейтинг пользователя.

    Args:
        user_id: UUID пользователя.
        new_rating: новый рейтинг (один отзыв).

    Использует admin_request для обхода RLS (вызывается от лица rat'ера, не владельца профиля).
    """
    ratings_resp = supabase_admin_request('GET', f'ratings?rated_user_id=eq.{user_id}&select=rating')
    if not ratings_resp.ok or not ratings_resp.json():
        return

    ratings_list = ratings_resp.json()
    total = sum(r['rating'] for r in ratings_list)
    avg = round(total / len(ratings_list), 1)

    supabase_admin_request('PATCH', f'profiles?id=eq.{user_id}', json={'rating': avg})


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
_ALLOWED_CHARS = set(
    'abcdefghijklmnopqrstuvwxyz'
    'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    '0123456789'
    'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
    'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ'
    ' -_.,:;!?@/#&()[]{}|+=\'"`~<>%^*$'
)


def sanitize_postgrest(value: Any) -> Any:
    """Экранировать спецсимволы PostgREST в пользовательском вводе.

    Этапы:
    1. URL-декодирование (%20 → пробел, %27 → ' и т.д.)
    2. Удаление опасных символов: ( ) , ; " ' &
    3. Экранирование спецсимволов PostgREST: . → \\. , * → \\*
    4. Whitelist-проверка: только разрешённые символы
    5. Обрезка пробелов

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

    # 2. Удаляем опасные символы, которые могут изменить структуру запроса
    for ch in '(),;"\'&':
        value = value.replace(ch, '')

    # 3. Экранируем спецсимволы PostgREST (удвоение точки, звёздочка через backslash)
    value = value.replace('.', '\\.').replace('*', '\\*')

    # 4. Whitelist-проверка: удаляем все символы не из разрешённого набора
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
