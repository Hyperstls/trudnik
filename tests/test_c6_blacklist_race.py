"""
C6: Race condition в blacklist

Тесты проверяют, что block_user:
- Правильно обрабатывает duplicate (race condition при параллельных запросах)
- Возвращает success для дубликатов в AJAX-запросах
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def employer_session(app_client):
    """Сессия авторизованного работодателя."""
    import jwt
    from app.config import Config
    import time
    
    payload = {
        'user_id': '66666666-6666-6666-6666-666666666666',
        'role': 'employer',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-bl'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '66666666-6666-6666-6666-666666666666'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-bl'
    return app_client


class TestBlacklistRaceCondition:
    """Тесты для blacklist без race condition."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.blacklist.postgrest_request')
    def test_block_user_success(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C6: block_user должен успешно блокировать."""
        mock_request.return_value = MagicMock(ok=True)

        target_id = '77777777-7777-7777-7777-777777777777'
        response = employer_session.post(
            f'/blacklist/{target_id}',
            headers={'X-CSRF-Token': 'test-csrf-token', 'X-Requested-With': 'XMLHttpRequest'},
            follow_redirects=False
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.blacklist.postgrest_request')
    def test_block_user_handles_duplicate_ajax(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C6: block_user должен обрабатывать duplicate в AJAX (race condition)."""
        # B12: PostgREST v14 возвращает 400 + code=23505 для unique-violation (не 409)
        mock_request.return_value = MagicMock(
            ok=False,
            status_code=400,
            json=lambda: {'code': '23505', 'message': 'duplicate key value violates unique constraint'}
        )

        target_id = '77777777-7777-7777-7777-777777777777'
        response = employer_session.post(
            f'/blacklist/{target_id}',
            headers={'X-CSRF-Token': 'test-csrf-token', 'X-Requested-With': 'XMLHttpRequest'},
            follow_redirects=False
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'уже' in data['message'].lower()

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.blacklist.postgrest_request')
    def test_block_user_handles_duplicate_form(
        self, mock_request, mock_blacklist, employer_session
    ):
        """C6: block_user должен обрабатывать duplicate в form-запросе."""
        mock_request.return_value = MagicMock(
            ok=False,
            status_code=409,
            text='duplicate key value violates unique constraint'
        )

        target_id = '77777777-7777-7777-7777-777777777777'
        response = employer_session.post(
            f'/blacklist/{target_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        # Должен редиректить (не падать)
        assert response.status_code == 302
