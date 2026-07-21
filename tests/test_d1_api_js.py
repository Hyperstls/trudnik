"""
Тесты для D1: apiFetch wrapper в static/js/api.js

Проверяет:
- Файл существует
- Содержит функцию generateUUID
- Содержит функцию apiFetch
- Добавляет X-Client-Request-Id для мутирующих запросов
- Добавляет X-CSRF-Token для мутирующих запросов
"""

import os
import re


def test_api_js_exists():
    """D1: файл static/js/api.js существует."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    assert os.path.exists(api_js_path), f"Файл {api_js_path} не найден"


def test_api_js_contains_generate_uuid():
    """D1: api.js содержит функцию generateUUID."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    with open(api_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'function generateUUID' in content, "Функция generateUUID не найдена в api.js"
    assert 'crypto.randomUUID' in content, "generateUUID должен использовать crypto.randomUUID"


def test_api_js_contains_api_fetch():
    """D1: api.js содержит функцию apiFetch."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    with open(api_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'async function apiFetch' in content, "Функция apiFetch не найдена в api.js"


def test_api_js_adds_client_request_id():
    """D1: apiFetch добавляет X-Client-Request-Id для мутирующих запросов."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    with open(api_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'X-Client-Request-Id' in content, "X-Client-Request-Id не найден в api.js"
    assert 'isMutating' in content, "Проверка isMutating не найдена"
    assert re.search(r"POST.*PUT.*PATCH.*DELETE|DELETE.*PATCH.*PUT.*POST", content, re.DOTALL), \
        "Не найдена проверка мутирующих методов (POST/PUT/PATCH/DELETE)"


def test_api_js_adds_csrf_token():
    """D1: apiFetch добавляет X-CSRF-Token для мутирующих запросов."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    with open(api_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'X-CSRF-Token' in content, "X-CSRF-Token не найден в api.js"
    assert 'csrf-token' in content, "meta[name='csrf-token'] не найден"


def test_api_js_handles_401():
    """D1: apiFetch обрабатывает 401 (редирект на /login)."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    with open(api_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'response.status === 401' in content, "Обработка 401 не найдена"
    assert '/login' in content, "Редирект на /login не найден"


def test_api_js_exports_functions():
    """D1: apiFetch и generateUUID экспортируются в window."""
    api_js_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'js', 'api.js')
    with open(api_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    assert 'window.apiFetch' in content, "Экспорт window.apiFetch не найден"
    assert 'window.generateUUID' in content, "Экспорт window.generateUUID не найден"
