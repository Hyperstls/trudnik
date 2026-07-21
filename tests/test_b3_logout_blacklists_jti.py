"""Тест B3: Инвалидация JWT при logout.

Проверяет что:
1. При logout jti добавляется в blacklist
2. Сессия очищается
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
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


def test_logout_blacklists_jti(client, app, mocker):
    """Тест 1: При logout jti должен быть добавлен в blacklist."""
    # Мокаем blacklist_jti в app.utils.auth
    mock_blacklist = mocker.patch('app.utils.auth.blacklist_jti')
    
    # Устанавливаем сессию с jti
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
        sess['email'] = 'test@example.com'
        sess['jti'] = 'test-jti-456'
    
    # Отправляем запрос на logout
    response = client.post('/logout', follow_redirects=True)
    
    # Проверяем что blacklist_jti был вызван с правильным jti
    mock_blacklist.assert_called_once_with('test-jti-456')


def test_logout_clears_session(client, app, mocker):
    """Тест 2: При logout сессия должна быть очищена."""
    # Мокаем blacklist_jti
    mocker.patch('app.utils.auth.blacklist_jti')
    
    # Устанавливаем сессию
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
        sess['email'] = 'test@example.com'
        sess['jti'] = 'test-jti-789'
    
    # Отправляем запрос на logout
    response = client.post('/logout', follow_redirects=True)
    
    # Проверяем что сессия очищена
    with client.session_transaction() as sess:
        assert 'user_id' not in sess
        assert 'role' not in sess
        assert 'email' not in sess
        assert 'jti' not in sess


def test_logout_without_jti(client, app, mocker):
    """Тест 3: Logout без jti должен работать без ошибок."""
    # Мокаем blacklist_jti
    mock_blacklist = mocker.patch('app.utils.auth.blacklist_jti')
    
    # Устанавливаем сессию без jti
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
    
    # Отправляем запрос на logout
    response = client.post('/logout', follow_redirects=True)
    
    # Проверяем что blacklist_jti не был вызван
    mock_blacklist.assert_not_called()
    
    # Проверяем что сессия очищена
    with client.session_transaction() as sess:
        assert 'user_id' not in sess
