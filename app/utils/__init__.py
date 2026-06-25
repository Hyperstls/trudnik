"""Пакет app.utils — ре-экспорт из специализированных модулей для обратной совместимости.

Все функции, ранее доступные через `from app.utils import ...`, продолжают работать.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 1. Сначала настраиваем mock-зависимости (до импорта postgrest-подмодуля)
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from app.testing.mock_postgrest import (
        _test_db,
        _uuid_counter,
        _gen_uuid,
        _test_auth_tokens,
        _MockRequestsResponse,
        _should_intercept,
        _mock_post,
        _mock_delete,
        _install_auth_mock,
        _uninstall_auth_mock,
        _is_mock_enabled,
        _test_mock_request,
        _test_mock_rpc,
        _reset_test_db,
        _seed_test_db,
    )

    # Устанавливаем перехватчик, если mock включён
    if _is_mock_enabled():
        _install_auth_mock()
    _mock_available = True
except Exception:
    _test_db = {}
    _uuid_counter = 0
    _gen_uuid = lambda: ''
    _test_auth_tokens = {}
    _MockRequestsResponse = None
    _should_intercept = lambda *a, **kw: False
    _mock_post = lambda *a, **kw: None
    _mock_delete = lambda *a, **kw: None
    _install_auth_mock = lambda: None
    _uninstall_auth_mock = lambda: None
    _is_mock_enabled = lambda: False
    _test_mock_request = lambda *a, **kw: None
    _test_mock_rpc = lambda *a, **kw: None
    _reset_test_db = lambda: None
    _seed_test_db = lambda *a, **kw: None
    _mock_available = False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Импортируем подмодули и инжектим mock-зависимости в postgrest
# ═══════════════════════════════════════════════════════════════════════════════

from app.utils import postgrest_client as _pgrest

# Инжектим mock-зависимости в модуль postgrest
_pgrest._test_db = _test_db
_pgrest._uuid_counter = _uuid_counter
_pgrest._gen_uuid = _gen_uuid
_pgrest._test_auth_tokens = _test_auth_tokens
_pgrest._MockRequestsResponse = _MockRequestsResponse
_pgrest._should_intercept = _should_intercept
_pgrest._mock_post = _mock_post
_pgrest._mock_delete = _mock_delete
_pgrest._install_auth_mock = _install_auth_mock
_pgrest._uninstall_auth_mock = _uninstall_auth_mock
_pgrest._is_mock_enabled = _is_mock_enabled
_pgrest._test_mock_request = _test_mock_request
_pgrest._test_mock_rpc = _test_mock_rpc
_pgrest._reset_test_db = _reset_test_db
_pgrest._seed_test_db = _seed_test_db

from app.utils import geo as _geo
from app.utils import formatting as _formatting
from app.utils import security as _security
from app.utils import business as _business
from app.utils import helpers as _helpers
from app.utils import auth as _auth
from app.utils import validators as _validators
from app.utils import rate_limit as _rate_limit_mod

# Сервисы (логически относятся к app.services, но ре-экспортируются
# через app.utils для обратной совместимости)
from app.services import storage_service as _storage_service
from app.services import ratings_service as _ratings_service
from app.services.push_service import PushService


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Ре-экспорт всего для обратной совместимости
# ═══════════════════════════════════════════════════════════════════════════════

# --- PostgREST клиент ---
CircuitBreaker = _pgrest.CircuitBreaker
PostgrestResponse = _pgrest.PostgrestResponse
cache_for = _pgrest.cache_for
POSTGREST_URL = _pgrest.POSTGREST_URL
PGRST_JWT_SECRET = _pgrest.PGRST_JWT_SECRET
get_service_role_headers = _pgrest.get_service_role_headers
get_user_headers = _pgrest.get_user_headers
refresh_access_token = _pgrest.refresh_access_token
postgrest_request = _pgrest.postgrest_request
postgrest_admin_request = _pgrest.postgrest_admin_request
postgrest_rpc = _pgrest.postgrest_rpc
generate_vapid_keys = PushService.generate_vapid_keys

# --- Гео-вычисления ---
calculate_distance = _geo.calculate_distance
filter_by_radius = _geo.filter_by_radius

# --- Форматирование ---
format_datetime = _formatting.format_datetime
format_date = _formatting.format_date
format_currency = _formatting.format_currency
truncate = _formatting.truncate
pluralize = _formatting.pluralize

# --- Безопасность ---
sanitize_postgrest = _security.sanitize_postgrest
sanitize_html = _security.sanitize_html
validate_uuid = _security.validate_uuid
generate_csrf_token = _security.generate_csrf_token

# --- Бизнес-хелперы ---
copy_job = _business.copy_job
check_withdraw_window = _business.check_withdraw_window

# --- Короткие хелперы ---
rate_limit = _rate_limit_mod.rate_limit
uid = _helpers.uid
my_query = _helpers.my_query

# --- Аутентификация ---
refresh_access_token = _auth.refresh_access_token
get_user_role = _auth.get_user_role
get_user_profile = _auth.get_user_profile
generate_jwt = _auth.generate_jwt

# --- Валидация ---
validate_password = _validators.validate_password
_SQL_INJECTION_PATTERNS = _validators._SQL_INJECTION_PATTERNS

# --- Загрузка файлов ---
MAX_UPLOAD_SIZE = _storage_service.MAX_UPLOAD_SIZE
upload_to_storage = _storage_service.upload_to_storage
upload_photo = _storage_service.upload_photo
delete_from_storage = _storage_service.delete_from_storage

# --- Рейтинги ---
update_rating = _ratings_service.update_rating
get_user_rating = _ratings_service.get_user_rating


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Экспортируем всё через __all__ для явного контракта
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # PostgREST
    'CircuitBreaker', 'PostgrestResponse',
    'cache_for',
    'POSTGREST_URL', 'PGRST_JWT_SECRET',
    'get_service_role_headers', 'get_user_headers',
    'postgrest_request', 'postgrest_admin_request', 'postgrest_rpc',
    'generate_vapid_keys',
    # Auth
    'refresh_access_token', 'get_user_role', 'get_user_profile', 'generate_jwt',
    # Validators
    'validate_password', '_SQL_INJECTION_PATTERNS',
    # Storage
    'MAX_UPLOAD_SIZE', 'upload_to_storage', 'upload_photo', 'delete_from_storage',
    # Ratings
    'update_rating', 'get_user_rating',
    # Geo
    'calculate_distance', 'filter_by_radius',
    # Formatting
    'format_datetime', 'format_date', 'format_currency', 'truncate', 'pluralize',
    # Security
    'sanitize_postgrest', 'sanitize_html', 'validate_uuid', 'generate_csrf_token',
    # Business
    'copy_job', 'check_withdraw_window',
    # Helpers
    'rate_limit', 'uid', 'my_query',
    # Mock (for testing)
    '_test_db', '_uuid_counter', '_gen_uuid',
    '_test_auth_tokens', '_MockRequestsResponse',
    '_should_intercept', '_mock_post', '_mock_delete',
    '_install_auth_mock', '_uninstall_auth_mock',
    '_is_mock_enabled', '_test_mock_request', '_test_mock_rpc',
    '_reset_test_db', '_seed_test_db',
]
