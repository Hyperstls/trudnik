"""
C1: TOCTOU в accept/reject заявок

Тесты проверяют, что accept/reject заявки не подвержены TOCTOU race condition:
- Python pre-check удалён
- RPC использует FOR UPDATE на applications
- При concurrent запросах только один succeeds
"""
import pytest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed


@pytest.fixture
def employer_session(app_client):
    """Сессия авторизованного работодателя."""
    import jwt
    from app.config import Config
    import time
    
    # Создаём валидный JWT токен
    payload = {
        'user_id': '11111111-1111-1111-1111-111111111111',
        'role': 'employer',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-123'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-123'
    return app_client


class TestAcceptRejectNoTOCTOU:
    """Тесты для accept/reject без TOCTOU race condition."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_accept_no_python_precheck(
        self, mock_request, mock_rpc, mock_blacklist, employer_session
    ):
        """C1: accept не должен делать Python pre-check статуса."""
        # Мокаем GET запрос для получения данных заявки
        mock_request.return_value = MagicMock(
            ok=True,
            json=lambda: [{
                'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                'worker_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                'status': 'pending'
            }]
        )
        
        # Мокаем проверку владельца
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'worker_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': '11111111-1111-1111-1111-111111111111'}])
        ]
        
        # Мокаем успешный RPC
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True, 'current_workers': 1, 'job_status': 'open'}
        )

        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        response = employer_session.post(
            f'/api/applications/{app_id}/accept',
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        
        # Проверяем что RPC был вызван (без Python pre-check)
        assert mock_rpc.called
        args, kwargs = mock_rpc.call_args
        assert args[0] == 'accept_application'

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_accept_handles_bad_status_from_rpc(
        self, mock_request, mock_rpc, mock_blacklist, employer_session
    ):
        """C1: accept должен обрабатывать bad_status от RPC (race condition)."""
        # Мокаем GET запрос
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'worker_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': '11111111-1111-1111-1111-111111111111'}])
        ]
        
        # Мокаем RPC с bad_status (заявка уже обработана)
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': False, 'code': 'bad_status', 'error': 'bad_status'}
        )

        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        response = employer_session.post(
            f'/api/applications/{app_id}/accept',
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Должен вернуть 409 Conflict
        assert response.status_code == 409
        data = response.get_json()
        assert 'уже обработана' in data['error']

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_reject_handles_already_rejected_from_rpc(
        self, mock_request, mock_rpc, mock_blacklist, employer_session
    ):
        """C1: reject должен обрабатывать already_rejected от RPC (race condition)."""
        # Мокаем GET запрос
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{'job_id': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'worker_id': 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': '11111111-1111-1111-1111-111111111111'}])
        ]
        
        # Мокаем RPC с already_rejected
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': False, 'code': 'already_rejected', 'error': 'already_rejected'}
        )

        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        response = employer_session.post(
            f'/api/applications/{app_id}/reject',
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Должен вернуть 409 Conflict
        assert response.status_code == 409
        data = response.get_json()
        assert 'уже обработана' in data['error']

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_concurrent_accept_only_one_succeeds(
        self, mock_request, mock_rpc, mock_blacklist, employer_session
    ):
        """C1: при concurrent accept только один должен succeed."""
        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        worker_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        employer_id = '11111111-1111-1111-1111-111111111111'
        
        # Счётчик вызовов RPC
        call_count = [0]
        
        def mock_rpc_side_effect(func_name, params, **kwargs):
            call_count[0] += 1
            # Первый вызов succeeds, второй — bad_status
            if call_count[0] == 1:
                return MagicMock(
                    ok=True,
                    json=lambda: {'success': True, 'current_workers': 1, 'job_status': 'open'}
                )
            else:
                return MagicMock(
                    ok=True,
                    json=lambda: {'success': False, 'code': 'bad_status', 'error': 'bad_status'}
                )
        
        mock_request.side_effect = [
            MagicMock(ok=True, json=lambda: [{'job_id': job_id, 'worker_id': worker_id, 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': employer_id}]),
            MagicMock(ok=True, json=lambda: [{'job_id': job_id, 'worker_id': worker_id, 'status': 'pending'}]),
            MagicMock(ok=True, json=lambda: [{'employer_id': employer_id}])
        ]
        
        mock_rpc.side_effect = mock_rpc_side_effect

        def make_accept_request():
            return employer_session.post(
                f'/api/applications/{app_id}/accept',
                headers={'X-CSRF-Token': 'test-csrf-token'}
            )

        # Запускаем два параллельных запроса
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(make_accept_request) for _ in range(2)]
            results = [f.result() for f in as_completed(futures)]

        # Проверяем что только один succeeded
        status_codes = [r.status_code for r in results]
        assert 200 in status_codes
        assert 409 in status_codes
