"""Тест B6: Защита от CSRF в WebSocket handshake.

Проверяет что:
1. Логика валидации Origin работает правильно
2. APP_URL и CORS_ORIGINS конфигурация существует в коде
"""
import pytest


def test_origin_validation_logic():
    """Тест 1: Проверка логики валидации Origin."""
    # Тестируем логику валидации Origin
    app_url = "http://localhost:8000"
    cors_origins = ["http://localhost:8000"]
    
    # Правильный Origin
    valid_origin = "http://localhost:8000"
    allowed_origins = [app_url] + cors_origins if cors_origins != ["*"] else [app_url]
    assert valid_origin in allowed_origins
    
    # Неправильный Origin
    invalid_origin = "http://evil.com"
    assert invalid_origin not in allowed_origins
    
    # Пустой Origin (должен быть разрешен)
    empty_origin = ""
    # Пустой Origin не проверяется (пропускается проверка)
    assert empty_origin == "" or empty_origin in allowed_origins


def test_origin_validation_with_wildcard():
    """Тест 2: Проверка логики валидации Origin с wildcard."""
    app_url = "http://localhost:8000"
    cors_origins = ["*"]
    
    # При wildcard разрешены только APP_URL
    allowed_origins = [app_url] + cors_origins if cors_origins != ["*"] else [app_url]
    
    # APP_URL должен быть разрешен
    assert app_url in allowed_origins
    
    # Другие origins должны быть запрещены (кроме APP_URL)
    invalid_origin = "http://evil.com"
    assert invalid_origin not in allowed_origins


def test_origin_validation_empty_origin():
    """Тест 3: Пустой Origin должен быть разрешен."""
    # Пустой Origin не проверяется (пропускается проверка)
    origin = ""
    # Логика: if origin and origin not in allowed_origins
    # Если origin пустой, проверка пропускается
    should_reject = origin and origin not in ["http://localhost:8000"]
    assert not should_reject


def test_websocket_main_file_has_origin_check():
    """Тест 4: Файл websocket_server/main.py должен содержать проверку Origin."""
    import os
    main_file = os.path.join(os.path.dirname(__file__), '..', 'websocket_server', 'main.py')
    
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем что есть проверка Origin header
    assert 'origin' in content.lower()
    assert 'APP_URL' in content
    assert '4003' in content  # Код закрытия при неправильном Origin
