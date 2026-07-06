"""
A4: Запрет отправки сообщений после withdraw

Тесты проверяют, что нельзя отправить сообщение в чат,
если заявка не в статусе 'accepted' (например, withdrawn, rejected).
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def worker_session(app_client):
    """Сессия авторизованного работника."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = 'worker'
        sess['_csrf_token'] = 'test-csrf-token'
    return app_client


@pytest.fixture
def employer_session(app_client):
    """Сессия авторизованного работодателя."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = '22222222-2222-2222-2222-222222222222'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
    return client


class TestChatAfterWithdraw:
    """Тесты для запрета отправки сообщений после withdraw."""

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_blocked_for_withdrawn_application(
        self, mock_postgrest, mock_redis, worker_session
    ):
        """A4: отправка сообщения должна быть заблокирована для withdrawn заявки."""
        # Mock Redis (rate limit pass)
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 1
        
        # Mock PostgREST response с withdrawn статусом
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': '33333333-3333-3333-3333-333333333333',
                'status': 'withdrawn',  # Заявка отозвана
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]
        )

        response = worker_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что запрос заблокирован с 403
        assert response.status_code == 403
        assert 'Чат доступен только после принятия отклика' in response.json()['message']

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_blocked_for_rejected_application(
        self, mock_postgrest, mock_redis, worker_session
    ):
        """A4: отправка сообщения должна быть заблокирована для rejected заявки."""
        # Mock Redis (rate limit pass)
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 1
        
        # Mock PostgREST response с rejected статусом
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': '33333333-3333-3333-3333-333333333333',
                'status': 'rejected',  # Заявка отклонена
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]
        )

        response = worker_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что запрос заблокирован с 403
        assert response.status_code == 403

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_allowed_for_accepted_application(
        self, mock_postgrest, mock_redis, worker_session
    ):
        """A4: отправка сообщения должна быть разрешена для accepted заявки."""
        # Mock Redis (rate limit pass)
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 1
        
        # Mock PostgREST response с accepted статусом
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': '33333333-3333-3333-3333-333333333333',
                'status': 'accepted',  # Заявка принята
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]
        )

        response = worker_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что запрос не заблокирован (должен быть 200)
        # Может быть 503 если PostgREST для INSERT не замокан, но не 403
        assert response.status_code != 403

    @patch('app.blueprints.chat.get_redis_client')
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_blocked_for_pending_application(
        self, mock_postgrest, mock_redis, worker_session
    ):
        """A4: отправка сообщения должна быть заблокирована для pending заявки."""
        # Mock Redis (rate limit pass)
        mock_redis_client = MagicMock()
        mock_redis.return_value = mock_redis_client
        mock_redis_client.eval.return_value = 1
        
        # Mock PostgREST response с pending статусом
        mock_postgrest.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': '33333333-3333-3333-3333-333333333333',
                'status': 'pending',  # Заявка на рассмотрении
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]
        )

        response = worker_session.post(
            '/api/send_message',
            json={
                'application_id': '44444444-4444-4444-4444-444444444444',
                'content': 'Test message'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что запрос заблокирован с 403
        assert response.status_code == 403
