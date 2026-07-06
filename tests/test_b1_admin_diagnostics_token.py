"""Тест B1: Исправление empty-token bypass в admin_diagnostics.

Проверяет что:
1. При пустом ADMIN_API_TOKEN запрос отклоняется
2. При неправильном токене запрос отклоняется
3. При правильном токене запрос проходит
"""
import pytest
from flask import Flask


@pytest.fixture
def app():
    """Создать тестовое приложение Flask."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['ADMIN_API_TOKEN'] = 'test-secret-token'
    
    # Регистрируем blueprint
    from app.blueprints.admin_diagnostics import admin_diagnostics_bp
    app.register_blueprint(admin_diagnostics_bp)
    
    return app


@pytest.fixture
def client(app):
    """Создать тестовый клиент."""
    return app.test_client()


def test_empty_token_rejected(client, app):
    """Тест 1: Пустой токен должен быть отклонён."""
    # Устанавливаем ADMIN_API_TOKEN в пустую строку
    app.config['ADMIN_API_TOKEN'] = ''
    
    # Пытаемся получить доступ с пустым токеном
    response = client.get(
        '/admin/api/migrations-status',
        headers={'X-Admin-Token': ''}
    )
    
    # Должен вернуть 401
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False
    assert 'Unauthorized' in data['error']


def test_wrong_token_rejected(client):
    """Тест 2: Неправильный токен должен быть отклонён."""
    response = client.get(
        '/admin/api/migrations-status',
        headers={'X-Admin-Token': 'wrong-token'}
    )
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False
    assert 'Unauthorized' in data['error']


def test_correct_token_accepted(client, app, mocker):
    """Тест 3: Правильный токен должен быть принят."""
    # Мокаем postgrest_admin_request чтобы не делать реальный запрос
    mock_resp = mocker.Mock()
    mock_resp.ok = True
    mock_resp.json.return_value = []
    
    mocker.patch(
        'app.blueprints.admin_diagnostics.postgrest_admin_request',
        return_value=mock_resp
    )
    
    response = client.get(
        '/admin/api/migrations-status',
        headers={'X-Admin-Token': 'test-secret-token'}
    )
    
    # Должен вернуть 200
    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] is True


def test_reset_circuit_breaker_empty_token_rejected(client, app):
    """Тест 4: reset-circuit-breaker с пустым токеном должен быть отклонён."""
    app.config['ADMIN_API_TOKEN'] = ''
    
    response = client.post(
        '/admin/api/reset-circuit-breaker',
        headers={'X-Admin-Token': ''}
    )
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False
    assert 'Unauthorized' in data['error']


def test_reset_circuit_breaker_wrong_token_rejected(client):
    """Тест 5: reset-circuit-breaker с неправильным токеном должен быть отклонён."""
    response = client.post(
        '/admin/api/reset-circuit-breaker',
        headers={'X-Admin-Token': 'wrong-token'}
    )
    
    assert response.status_code == 401
    data = response.get_json()
    assert data['success'] is False
    assert 'Unauthorized' in data['error']
