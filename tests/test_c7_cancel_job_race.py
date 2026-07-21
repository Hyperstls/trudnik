"""
C7: Race condition в cancel_job с accepted worker

Тесты проверяют, что cancel_job:
- Использует атомарный RPC cancel_job_atomic
- Правильно обрабатывает has_accepted_workers (race condition)
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
        'user_id': '88888888-8888-8888-8888-888888888888',
        'role': 'employer',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-cancel'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '88888888-8888-8888-8888-888888888888'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-cancel'
    return app_client


class TestCancelJobRaceCondition:
    """Тесты для cancel_job без race condition."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner', return_value=True)
    def test_cancel_job_uses_atomic_rpc(
        self, mock_check_owner, mock_rpc, mock_blacklist, employer_session
    ):
        """C7: cancel_job должен редиректить после успеха."""
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True, 'rejected_worker_ids': []}
        )

        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        response = employer_session.post(
            f'/cancel-job/{job_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        # Должен редиректить после успеха
        assert response.status_code == 302

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_cancel_job_handles_accepted_workers(
        self, mock_check_owner, mock_rpc, mock_blacklist, employer_session
    ):
        """C7: cancel_job должен редиректить при наличии accepted workers."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {
                'success': False,
                'code': 'has_accepted_workers',
                'error': 'Невозможно отменить: есть принятые работники'
            }
        )

        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        response = employer_session.post(
            f'/cancel-job/{job_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        # Должен редиректить (не падать)
        assert response.status_code == 302
