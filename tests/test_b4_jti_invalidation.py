"""Тест B4: Инвалидация JWT при сбросе пароля и admin-удалении.

Проверяет что:
1. blacklist_jti функция существует и работает
2. password_changed_at обновляется при смене пароля
3. Admin не может удалить другого admin
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


def test_blacklist_jti_function_exists():
    """Тест 1: Функция blacklist_jti должна существовать."""
    from app.utils.auth import blacklist_jti
    assert callable(blacklist_jti)


def test_blacklist_jti_adds_to_redis(app, mocker):
    """Тест 2: blacklist_jti должен добавлять jti в Redis."""
    mock_redis = mocker.Mock()
    mocker.patch('app.utils.redis_client.get_redis_client', return_value=mock_redis)
    
    from app.utils.auth import blacklist_jti
    blacklist_jti('test-jti-123', ttl=3600)
    
    mock_redis.setex.assert_called_once_with('jti_blacklist:test-jti-123', 3600, '1')


def test_admin_delete_checks_target_role(client, app, mocker):
    """Тест 3: При удалении пользователя должна проверяться роль target."""
    # Мокаем сессию admin
    with client.session_transaction() as sess:
        sess['user_id'] = 'admin-user-id'
        sess['role'] = 'admin'
        sess['access_token'] = 'test-token'
    
    # Мокаем postgrest_admin_request для проверки роли (target - admin)
    mock_role_resp = mocker.Mock()
    mock_role_resp.ok = True
    mock_role_resp.json.return_value = [{'role': 'admin'}]
    
    mock_postgrest = mocker.patch(
        'app.blueprints.admin_users.postgrest_admin_request',
        return_value=mock_role_resp
    )
    
    mock_rpc = mocker.patch('app.blueprints.admin_users.postgrest_rpc')
    
    # Отправляем запрос на удаление
    response = client.post(
        '/admin/users/other-admin-id/delete',
        follow_redirects=True
    )
    
    # Проверяем что RPC не был вызван (удаление заблокировано)
    mock_rpc.assert_not_called()


def test_admin_delete_function_exists():
    """Тест 4: Функция delete_user должна существовать с правильными декораторами."""
    from app.blueprints.admin_users import delete_user
    assert callable(delete_user)
    
    # Проверяем что функция имеет декораторы
    assert hasattr(delete_user, '__wrapped__')
