"""
E4: Тест для /health endpoint.

Endpoint должен проверять работоспособность БД, Redis и Circuit Breaker.
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


class TestHealthEndpoint:
    """Тесты для /health."""
    
    def test_health_endpoint_exists(self, client):
        """Endpoint /health должен существовать."""
        response = client.get('/health')
        
        assert response.status_code == 200
    
    def test_health_returns_json(self, client):
        """Endpoint должен возвращать JSON."""
        response = client.get('/health')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data is not None
    
    def test_health_contains_status(self, client):
        """Ответ должен содержать поле status."""
        response = client.get('/health')
        data = response.get_json()
        
        assert 'status' in data
        assert data['status'] in ('ok', 'degraded')
    
    def test_health_contains_database(self, client):
        """Ответ должен содержать поле database."""
        response = client.get('/health')
        data = response.get_json()
        
        assert 'database' in data
        assert data['database'] in ('ok', 'error')
    
    def test_health_contains_redis(self, client):
        """Ответ должен содержать поле redis."""
        response = client.get('/health')
        data = response.get_json()
        
        assert 'redis' in data
        assert data['redis'] in ('ok', 'error')
    
    def test_health_contains_circuit_breaker(self, client):
        """Ответ должен содержать поле circuit_breaker."""
        response = client.get('/health')
        data = response.get_json()
        
        assert 'circuit_breaker' in data
        assert 'postgrest' in data['circuit_breaker']
        assert 'admin' in data['circuit_breaker']
    
    def test_health_contains_timestamp(self, client):
        """Ответ должен содержать поле timestamp."""
        response = client.get('/health')
        data = response.get_json()
        
        assert 'timestamp' in data
    
    def test_health_contains_uptime(self, client):
        """Ответ должен содержать поле uptime_seconds."""
        response = client.get('/health')
        data = response.get_json()
        
        assert 'uptime_seconds' in data
        assert isinstance(data['uptime_seconds'], int)
        assert data['uptime_seconds'] >= 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
