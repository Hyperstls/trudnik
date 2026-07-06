"""Тест B10: Embed password_changed_at в JWT payload.

Проверяет что:
1. generate_jwt добавляет pwd_changed_at в payload
2. login_required проверяет pwd_changed_at
"""
import pytest
from datetime import datetime, timezone
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


def test_generate_jwt_includes_pwd_changed_at(app):
    """Тест 1: generate_jwt должен включать pwd_changed_at в payload."""
    from app.utils.auth import generate_jwt
    import jwt
    
    with app.app_context():
        pwd_changed = datetime.now(timezone.utc)
        token = generate_jwt('test-user-id', 'worker', password_changed_at=pwd_changed)
        
        # Декодируем токен
        payload = jwt.decode(token, app.config['PGRST_JWT_SECRET'], algorithms=['HS256'], 
                            options={'verify_aud': False})
        
        # Проверяем что pwd_changed_at присутствует
        assert 'pwd_changed_at' in payload
        assert payload['pwd_changed_at'] == pwd_changed.isoformat()


def test_generate_jwt_without_pwd_changed_at(app):
    """Тест 2: generate_jwt должен работать без pwd_changed_at."""
    from app.utils.auth import generate_jwt
    import jwt
    
    with app.app_context():
        token = generate_jwt('test-user-id', 'worker')
        
        # Декодируем токен
        payload = jwt.decode(token, app.config['PGRST_JWT_SECRET'], algorithms=['HS256'], 
                            options={'verify_aud': False})
        
        # Проверяем что pwd_changed_at отсутствует или None
        assert payload.get('pwd_changed_at') is None


def test_login_required_checks_pwd_changed_at(client, app, mocker):
    """Тест 3: login_required должен проверять pwd_changed_at."""
    # Мокаем redis_cache
    mock_get_cached = mocker.patch('app.utils.redis_cache.get_cached', return_value=None)
    mock_set_cached = mocker.patch('app.utils.redis_cache.set_cached')
    
    # Мокаем postgrest_request - возвращаем другое значение password_changed_at
    mock_resp = mocker.Mock()
    mock_resp.ok = True
    mock_resp.json.return_value = [{'password_changed_at': '2024-01-02T00:00:00+00:00'}]
    
    mocker.patch('app.utils.postgrest_request', return_value=mock_resp)
    
    # Создаем тестовый маршрут с login_required
    from app.decorators import login_required
    
    @app.route('/test-b10-pwd-changed')
    @login_required
    def test_route_pwd_changed():
        return 'OK'
    
    # Создаем токен с другим pwd_changed_at
    from app.utils.auth import generate_jwt
    with app.app_context():
        old_pwd_changed = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        token = generate_jwt('test-user-id', 'worker', password_changed_at=old_pwd_changed)
    
    # Мокаем сессию с токеном
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
        sess['access_token'] = token
    
    # Отправляем запрос
    response = client.get('/test-b10-pwd-changed')
    
    # Проверяем что произошел редирект на login (токен недействителен)
    assert response.status_code == 302
    assert '/login' in response.location


def test_login_required_allows_valid_pwd_changed_at(client, app, mocker):
    """Тест 4: login_required должен пропускать запрос если pwd_changed_at совпадает."""
    # Мокаем redis_cache
    mock_get_cached = mocker.patch('app.utils.redis_cache.get_cached', return_value=None)
    mock_set_cached = mocker.patch('app.utils.redis_cache.set_cached')
    
    # Мокаем postgrest_request - возвращаем разные данные для разных запросов
    pwd_changed = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    
    def mock_postgrest(method, path, **kwargs):
        mock_resp = mocker.Mock()
        mock_resp.ok = True
        if 'password_changed_at' in path:
            mock_resp.json.return_value = [{'password_changed_at': pwd_changed.isoformat()}]
        else:
            # Для проверки user_exists (select=id)
            mock_resp.json.return_value = [{'id': 'test-user-id'}]
        return mock_resp
    
    mocker.patch('app.utils.postgrest_request', side_effect=mock_postgrest)
    
    # Создаем тестовый маршрут с login_required
    from app.decorators import login_required
    
    @app.route('/test-b10-pwd-valid')
    @login_required
    def test_route_pwd_valid():
        return 'OK'
    
    # Создаем токен с тем же pwd_changed_at
    from app.utils.auth import generate_jwt
    with app.app_context():
        token = generate_jwt('test-user-id', 'worker', password_changed_at=pwd_changed)
    
    # Мокаем сессию с токеном
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-user-id'
        sess['role'] = 'worker'
        sess['access_token'] = token
    
    # Отправляем запрос
    response = client.get('/test-b10-pwd-valid')
    
    # Проверяем что запрос прошел успешно
    assert response.status_code == 200
    assert response.data == b'OK'
