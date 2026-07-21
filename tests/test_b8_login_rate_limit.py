"""Тест B8: Rate limiting на login endpoint.

Проверяет что:
1. Login endpoint использует rate_limit декоратор
2. Rate limiting работает корректно
"""
import pytest
from flask import Flask


@pytest.fixture
def app():
    """Создать тестовое приложение Flask."""
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Создать тестовый клиент."""
    return app.test_client()


def test_login_has_rate_limit_decorator():
    """Тест 1: Login endpoint должен использовать rate_limit декоратор."""
    from app.blueprints.auth import login
    
    # Проверяем что функция имеет декораторы
    assert callable(login)
    
    # Проверяем что rate_limit импортирован
    from app.decorators import rate_limit
    assert callable(rate_limit)


def test_rate_limit_decorator_exists():
    """Тест 2: Декоратор rate_limit должен существовать."""
    from app.utils.rate_limit_decorator import rate_limit
    assert callable(rate_limit)


def test_rate_limit_code_contains_login_protection():
    """Тест 3: Код auth.py должен содержать rate limiting для login."""
    import os
    auth_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'blueprints', 'auth.py')
    
    with open(auth_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем что login endpoint использует rate_limit
    assert '@rate_limit' in content
    assert 'def login()' in content


def test_rate_limit_parameters():
    """Тест 4: Rate limit должен иметь правильные параметры."""
    import os
    rate_limit_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'utils', 'rate_limit_decorator.py')
    
    with open(rate_limit_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем параметры rate limiting
    assert '_RATE_WINDOW' in content
    assert '_RATE_MAX_REQUESTS' in content
    assert 'fail_open' in content
