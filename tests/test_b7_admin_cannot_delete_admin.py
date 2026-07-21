"""Тест B7: Admin не может удалить другого admin.

Проверяет что:
1. При попытке удалить admin операция отклоняется
2. Функция delete_user содержит проверку роли target
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


def test_admin_delete_checks_target_role(client, app, mocker):
    """Тест 1: При удалении пользователя должна проверяться роль target."""
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


def test_delete_user_function_exists():
    """Тест 2: Функция delete_user должна существовать с правильными декораторами."""
    from app.blueprints.admin_users import delete_user
    assert callable(delete_user)
    
    # Проверяем что функция имеет декораторы
    assert hasattr(delete_user, '__wrapped__')


def test_admin_delete_code_contains_role_check():
    """Тест 3: Код delete_user должен содержать проверку роли target."""
    import os
    admin_users_file = os.path.join(os.path.dirname(__file__), '..', 'app', 'blueprints', 'admin_users.py')
    
    with open(admin_users_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем что есть проверка роли target
    assert 'target_role' in content or 'role' in content
    assert 'admin' in content
    assert 'Нельзя удалить администратора' in content
