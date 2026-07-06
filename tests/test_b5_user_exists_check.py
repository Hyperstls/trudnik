"""Тест B5: Проверка существования user_id в profiles в login_required.

Проверяет что:
1. get_cached и set_cached функции существуют
2. login_required использует кэширование
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


def test_get_cached_function_exists():
    """Тест 1: Функция get_cached должна существовать."""
    from app.utils.redis_cache import get_cached
    assert callable(get_cached)


def test_set_cached_function_exists():
    """Тест 2: Функция set_cached должна существовать."""
    from app.utils.redis_cache import set_cached
    assert callable(set_cached)


def test_login_required_uses_cache(client, app, mocker):
    """Тест 3: login_required должен использовать кэш."""
    # Мокаем redis_cache - пользователь существует в кэше
    mock_get_cached = mocker.patch('app.utils.redis_cache.get_cached', return_value=True)
    mock_set_cached = mocker.patch('app.utils.redis_cache.set_cached')
    
    # Мокаем postgrest_request (не должен вызываться)
    mock_postgrest = mocker.patch('app.utils.postgrest_request')
    
    # Создаем тестовый маршрут с login_required
    from app.decorators import login_required
    
    @app.route('/test-b5-cache')
    @login_required
    def test_route_cache():
        return 'OK'
    
    # Мокаем сессию с валидным токеном
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
        sess['access_token'] = 'test-token'
    
    # Отправляем запрос
    response = client.get('/test-b5-cache')
    
    # Проверяем что postgrest_request не был вызван (использован кэш)
    mock_postgrest.assert_not_called()


def test_login_required_clears_session_if_user_not_exists(client, app, mocker):
    """Тест 4: login_required должен очищать сессию если пользователь не существует."""
    # Мокаем redis_cache
    mock_get_cached = mocker.patch('app.utils.redis_cache.get_cached', return_value=None)
    mock_set_cached = mocker.patch('app.utils.redis_cache.set_cached')
    
    # Мокаем postgrest_request - пользователь не существует
    mock_resp = mocker.Mock()
    mock_resp.ok = True
    mock_resp.json.return_value = []
    
    mocker.patch('app.utils.postgrest_request', return_value=mock_resp)
    
    # Создаем тестовый маршрут с login_required
    from app.decorators import login_required
    
    @app.route('/test-b5-not-exists')
    @login_required
    def test_route_not_exists():
        return 'OK'
    
    # Мокаем сессию с валидным токеном
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
        sess['access_token'] = 'test-token'
    
    # Отправляем запрос
    response = client.get('/test-b5-not-exists')
    
    # Проверяем что произошел редирект на login
    assert response.status_code == 302
    assert '/login' in response.location
