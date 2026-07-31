"""Unit-тесты аутентификации: регистрация, вход, выход, защищённые маршруты."""

import pytest
from unittest.mock import patch, MagicMock


def test_register_page_loads(app_client):
    """Страница регистрации отдаёт 200."""
    response = app_client.get('/register')
    assert response.status_code == 200


def test_login_page_loads(app_client):
    """Страница входа отдаёт 200."""
    response = app_client.get('/login')
    assert response.status_code == 200


def test_register_weak_password(app_client):
    """Регистрация со слабым паролем отклоняется."""
    response = app_client.post('/register', data={
        'full_name': 'Test User',
        'email': 'test@example.com',
        'password': '123',  # слишком короткий
        'city': 'Москва',
        'role': 'worker',
        '_csrf_token': 'test',
    }, follow_redirects=True)
    # Должен вернуть 200 со страницей регистрации (с ошибкой)
    assert response.status_code == 200
    # Проверяем наличие сообщения об ошибке пароля
    assert 'Пароль'.encode('utf-8') in response.data or b'password' in response.data.lower()


def test_register_valid_password(app_client):
    """Регистрация с валидным паролем проходит валидацию."""
    response = app_client.post('/register', data={
        'full_name': 'Test User',
        'email': 'test@example.com',
        'password': 'StrongP@ss1',
        'city': 'Москва',
        'role': 'worker',
        '_csrf_token': 'test',
    }, follow_redirects=True)
    assert response.status_code == 200


def test_logout_redirects(app_client):
    """Выход редиректит на страницу входа (logout — POST-only)."""
    response = app_client.post('/logout', follow_redirects=False)
    assert response.status_code in [302, 303]


def test_protected_route_redirects(app_client):
    """Защищённые маршруты редиректят на логин."""
    response = app_client.get('/profile', follow_redirects=False)
    assert response.status_code in [302, 303]


def test_csrf_token_in_form(app_client):
    """CSRF токен присутствует в форме."""
    response = app_client.get('/login')
    assert response.status_code == 200
    assert b'csrf' in response.data.lower()
