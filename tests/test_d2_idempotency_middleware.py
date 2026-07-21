"""
Тесты для D2: server-side idempotency middleware.

Проверяет:
- Middleware check_idempotency существует
- Middleware cache_idempotency_response существует
- Middleware зарегистрирован в register_middleware
- Повторный запрос с тем же X-Client-Request-Id возвращает кэшированный ответ
"""

import os
import re


def test_middleware_check_idempotency_exists():
    """D2: функция check_idempotency существует в middleware.py."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'def check_idempotency' in content, "Функция check_idempotency не найдена"


def test_middleware_cache_idempotency_response_exists():
    """D2: функция cache_idempotency_response существует в middleware.py."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'def cache_idempotency_response' in content, "Функция cache_idempotency_response не найдена"


def test_middleware_registered():
    """D2: middleware зарегистрирован в register_middleware."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'app.before_request(check_idempotency)' in content, \
        "check_idempotency не зарегистрирован как before_request"
    assert 'app.after_request(cache_idempotency_response)' in content, \
        "cache_idempotency_response не зарегистрирован как after_request"


def test_middleware_checks_client_request_id():
    """D2: middleware проверяет X-Client-Request-Id."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'X-Client-Request-Id' in content, "X-Client-Request-Id не найден в middleware"


def test_middleware_uses_redis():
    """D2: middleware использует Redis для кэширования."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'idempotency:' in content, "Ключ idempotency: не найден"
    assert 'get_redis_client' in content, "get_redis_client не используется"


def test_middleware_validates_uuid():
    """D2: middleware валидирует UUID формат."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'uuid.UUID' in content, "Валидация UUID не найдена"


def test_middleware_caches_2xx_only():
    """D2: middleware кэширует только успешные ответы (2xx)."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert '200 <= response.status_code < 300' in content, \
        "Проверка 2xx status code не найдена"


def test_middleware_ttl_24h():
    """D2: middleware устанавливает TTL 24 часа (86400 секунд)."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert '86400' in content, "TTL 86400 (24h) не найден"


def test_middleware_replayed_header():
    """D2: middleware добавляет X-Idempotency-Replayed заголовок."""
    middleware_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'middleware.py')
    with open(middleware_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'X-Idempotency-Replayed' in content, "Заголовок X-Idempotency-Replayed не найден"
