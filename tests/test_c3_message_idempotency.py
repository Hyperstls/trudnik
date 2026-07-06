"""
C3: Идемпотентность сообщений в чате

Тесты проверяют, что:
- client_message_id валидируется как UUID
- При дубликате (unique constraint violation) возвращается существующее сообщение
- Обычные сообщения без client_message_id работают как раньше
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def user_session(app_client):
    """Сессия авторизованного пользователя."""
    import jwt
    from app.config import Config
    import time
    
    payload = {
        'user_id': '11111111-1111-1111-1111-111111111111',
        'role': 'worker',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-789'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = 'worker'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-789'
    return app_client


class TestChatMessageIdempotency:
    """Тесты для идемпотентности сообщений в чате."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_with_valid_client_message_id(
        self, mock_request, mock_blacklist, user_session
    ):
        """C3: сообщение с валидным client_message_id должно сохраняться."""
        # Мокаем проверку заявки
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                'status': 'accepted',
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]),
            MagicMock(ok=True, json=lambda: [{'id': 'msg-123'}])
        ]

        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
                'content': 'Привет!',
                'client_message_id': 'dddddddd-dddd-dddd-dddd-dddddddddddd'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_with_invalid_client_message_id(
        self, mock_request, mock_blacklist, user_session
    ):
        """C3: невалидный client_message_id должен вернуть 400."""
        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
                'content': 'Привет!',
                'client_message_id': 'not-a-uuid'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'invalid client_message_id' in data['error']

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_duplicate_returns_existing(
        self, mock_request, mock_blacklist, user_session
    ):
        """C3: при дубликате должно возвращаться существующее сообщение."""
        # Мокаем: проверка заявки, POST (ошибка unique), GET (существующее)
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                'status': 'accepted',
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]),
            MagicMock(ok=False, text='duplicate key value violates unique constraint'),
            MagicMock(ok=True, json=lambda: [{'id': 'existing-msg-123'}])
        ]

        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
                'content': 'Привет!',
                'client_message_id': 'dddddddd-dddd-dddd-dddd-dddddddddddd'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
        assert data['message_id'] == 'existing-msg-123'

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.chat.postgrest_request')
    def test_send_message_without_client_message_id(
        self, mock_request, mock_blacklist, user_session
    ):
        """C3: сообщение без client_message_id должно работать как раньше."""
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{
                'worker_id': '11111111-1111-1111-1111-111111111111',
                'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                'status': 'accepted',
                'job': {'employer_id': '22222222-2222-2222-2222-222222222222'}
            }]),
            MagicMock(ok=True, json=lambda: [{'id': 'msg-456'}])
        ]

        response = user_session.post(
            '/api/send_message',
            json={
                'application_id': 'cccccccc-cccc-cccc-cccc-cccccccccccc',
                'content': 'Привет!'
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'ok'
