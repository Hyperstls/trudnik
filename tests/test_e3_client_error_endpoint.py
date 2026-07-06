"""
E3: Тест для endpoint приёма frontend ошибок.

Endpoint /api/client-error должен принимать JSON с информацией об ошибке
и логировать её.
"""
import pytest
from app import create_app


@pytest.fixture
def client():
    """Создать тестовый клиент Flask."""
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestClientErrorEndpoint:
    """Тесты для /api/client-error."""
    
    def test_accepts_valid_error_report(self, client):
        """Endpoint должен принимать валидный отчёт об ошибке."""
        response = client.post('/api/client-error', json={
            'message': 'TypeError: undefined is not a function',
            'source': 'https://example.com/app.js',
            'lineno': 42,
            'colno': 10,
            'stack': 'TypeError: undefined is not a function\n    at app.js:42:10',
            'url': 'https://example.com/jobs',
            'userAgent': 'Mozilla/5.0'
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
    
    def test_accepts_empty_payload(self, client):
        """Endpoint должен принимать пустой payload."""
        response = client.post('/api/client-error', json={})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
    
    def test_accepts_no_json(self, client):
        """Endpoint должен принимать запрос без JSON."""
        response = client.post('/api/client-error')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
    
    def test_truncates_long_message(self, client):
        """Endpoint должен обрезать длинные сообщения."""
        long_message = 'A' * 1000
        response = client.post('/api/client-error', json={
            'message': long_message
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
    
    def test_truncates_long_stack(self, client):
        """Endpoint должен обрезать длинные стеки."""
        long_stack = 'A' * 2000
        response = client.post('/api/client-error', json={
            'stack': long_stack
        })
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
    
    def test_rejects_get_request(self, client):
        """Endpoint должен отклонять GET запросы."""
        response = client.get('/api/client-error')
        
        assert response.status_code == 405  # Method Not Allowed


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
