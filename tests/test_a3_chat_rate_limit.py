"""
A3: Атомарный rate limiter для chat через Lua-скрипт

Тесты проверяют, что rate limiter использует атомарный Lua-скрипт
вместо неатомарных INCR + EXPIRE операций.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def user_session(client):
    """Сессия авторизованного пользователя."""
    with client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = 'worker'
        sess['_csrf_token'] = 'test-csrf-token'
    return client


class TestChatRateLimitAtomic:
    """Тесты для атомарного rate limiter."""

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_rate_limit_uses_lua_script(self, mock_postgrest, mock_redis, user_session):
        """A3: rate limiter должен использовать Lua-скрипт через eval."""
        # Mock Redis client
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 1  # Первое сообщение - в пределах лимита
        
        # Mock PostgREST response
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': '22222222-2222-2222-2222-222222222222',
                'status': 'accepted',
                'job': {'employer_id': '33333333-3333-3333-3333-333333333333'}
            }]
        )

        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что был вызван eval с Lua-скриптом
        assert mock_redis_client.eval.called
        call_args = mock_redis_client.eval.call_args
        # Первый аргумент - Lua-скрипт
        assert 'INCR' in call_args[0][0]
        assert 'EXPIRE' in call_args[0][0]

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_rate_limit_blocks_after_limit(self, mock_postgrest, mock_redis, user_session):
        """A3: rate limiter должен блокировать после превышения лимита."""
        # Mock Redis client
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 6  # Превышен лимит (5 сообщений)

        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что запрос заблокирован
        assert response.status_code == 429
        assert 'Слишком много сообщений' in response.json()['error']

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_rate_limit_allows_within_limit(self, mock_postgrest, mock_redis, user_session):
        """A3: rate limiter должен разрешать сообщения в пределах лимита."""
        # Mock Redis client
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 3  # В пределах лимита
        
        # Mock PostgREST response
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': '22222222-2222-2222-2222-222222222222',
                'status': 'accepted',
                'job': {'employer_id': '33333333-3333-3333-3333-333333333333'}
            }]
        )

        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что запрос не заблокирован (должен быть 200 или redirect)
        assert response.status_code != 429

    @patch('app.blueprints.chat.get_redis_client')
    def test_rate_limit_fails_open_on_redis_error(self, mock_redis, user_session):
        """A3: при ошибке Redis rate limiter должен fail-open (разрешать)."""
        # Mock Redis client с ошибкой
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.side_effect = Exception("Redis connection error")

        # Проверяем что функция возвращает True (разрешить)
        from app.blueprints.chat import _check_chat_rate_limit
        result = _check_chat_rate_limit(
            mock_redis_client, 
            'user-id', 
            'app-id', 
            limit=5, 
            window=60
        )
        assert result is True  # Fail-open
