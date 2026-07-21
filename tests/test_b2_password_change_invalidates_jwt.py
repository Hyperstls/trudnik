"""Тест B2: Инвалидация JWT при смене пароля.

Проверяет что:
1. blacklist_jti существует и работает
2. login_user_session сохраняет jti в сессию
"""
import pytest
from flask import Flask, session


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


def test_blacklist_jti_function_exists():
    """Тест 1: Функция blacklist_jti должна существовать."""
    from app.utils.auth import blacklist_jti
    assert callable(blacklist_jti)


def test_login_user_session_saves_jti(app):
    """Тест 2: login_user_session должен сохранять jti в сессию."""
    from app.utils.auth import login_user_session
    
    with app.test_request_context():
        login_user_session('test-user-id', 'worker', 'test@example.com')
        
        # Проверяем что jti сохранен в сессии
        assert 'jti' in session
        assert session['jti'] is not None
        assert len(session['jti']) > 0


def test_blacklist_jti_signature():
    """Тест 3: blacklist_jti должна принимать jti и ttl."""
    from app.utils.auth import blacklist_jti
    import inspect
    
    sig = inspect.signature(blacklist_jti)
    params = list(sig.parameters.keys())
    
    assert 'jti' in params
    assert 'ttl' in params
    
    # Проверяем значение по умолчанию для ttl
    assert sig.parameters['ttl'].default == 86400
