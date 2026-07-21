"""Тест B9: Secure cookie flags.

Проверяет что:
1. SESSION_COOKIE_HTTPONLY = True
2. SESSION_COOKIE_SECURE = True
3. SESSION_COOKIE_SAMESITE = 'Strict'
4. SESSION_COOKIE_NAME установлен
5. PERMANENT_SESSION_LIFETIME установлен
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


def test_session_cookie_httponly(app):
    """Тест 1: SESSION_COOKIE_HTTPONLY должен быть True."""
    assert app.config.get('SESSION_COOKIE_HTTPONLY') is True


def test_session_cookie_secure(app):
    """Тест 2: SESSION_COOKIE_SECURE должен быть True."""
    assert app.config.get('SESSION_COOKIE_SECURE') is True


def test_session_cookie_samesite(app):
    """Тест 3: SESSION_COOKIE_SAMESITE должен быть 'Strict'."""
    assert app.config.get('SESSION_COOKIE_SAMESITE') == 'Strict'


def test_session_cookie_name(app):
    """Тест 4: SESSION_COOKIE_NAME должен быть установлен."""
    cookie_name = app.config.get('SESSION_COOKIE_NAME')
    assert cookie_name is not None
    assert isinstance(cookie_name, str)
    assert len(cookie_name) > 0


def test_permanent_session_lifetime(app):
    """Тест 5: PERMANENT_SESSION_LIFETIME должен быть установлен."""
    lifetime = app.config.get('PERMANENT_SESSION_LIFETIME')
    assert lifetime is not None
    assert isinstance(lifetime, (int, float))
    assert lifetime > 0


def test_config_file_contains_secure_cookie_settings():
    """Тест 6: Файл config.py должен содержать настройки secure cookies."""
    import os
    config_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'config.py')
    
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие всех необходимых настроек
    assert 'SESSION_COOKIE_HTTPONLY' in content
    assert 'SESSION_COOKIE_SECURE' in content
    assert 'SESSION_COOKIE_SAMESITE' in content
    assert 'SESSION_COOKIE_NAME' in content
    assert 'PERMANENT_SESSION_LIFETIME' in content
    
    # Проверяем значения
    assert 'True' in content  # HTTPONLY и SECURE должны быть True
    assert "'Strict'" in content or '"Strict"' in content  # SAMESITE должен быть Strict
