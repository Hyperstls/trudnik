"""
C2: Race condition в withdraw_application

Тесты проверяют, что withdraw_application:
- Использует атомарный RPC withdraw_application_atomic
- Правильно обрабатывает already_withdrawn (race condition)
- При concurrent запросах только один succeeds
"""
import pytest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed


@pytest.fixture
def worker_session(app_client):
    """Сессия авторизованного работника."""
    import jwt
    from app.config import Config
    import time
    
    # Создаём валидный JWT токен
    payload = {
        'user_id': '22222222-2222-2222-2222-222222222222',
        'role': 'worker',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-456'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '22222222-2222-2222-2222-222222222222'
        sess['role'] = 'worker'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-456'
    return app_client


class TestWithdrawApplicationAtomic:
    """Тесты для withdraw_application без race condition."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.services.application_service.postgrest_rpc')
    def test_withdraw_uses_atomic_rpc(
        self, mock_rpc, mock_blacklist, worker_session
    ):
        """C2: withdraw должен использовать withdraw_application_atomic RPC."""
        # Мокаем успешный RPC
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True, 'message': 'Заявка отозвана', 'new_status': 'withdrawn'}
        )

        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        response = worker_session.post(
            f'/api/applications/{app_id}/withdraw',
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        
        # Проверяем что вызван именно withdraw_application_atomic
        assert mock_rpc.called
        args, kwargs = mock_rpc.call_args
        assert args[0] == 'withdraw_application_atomic'
        assert 'p_application_id' in args[1]
        assert 'p_user_id' in args[1]

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.services.application_service.postgrest_rpc')
    def test_withdraw_handles_already_withdrawn(
        self, mock_rpc, mock_blacklist, worker_session
    ):
        """C2: withdraw должен обрабатывать already_withdrawn от RPC (race condition)."""
        # Мокаем RPC с already_withdrawn
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': False, 'code': 'already_withdrawn', 'error': 'Заявка уже отозвана'}
        )

        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        response = worker_session.post(
            f'/api/applications/{app_id}/withdraw',
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Должен вернуть 409 Conflict
        assert response.status_code == 409
        data = response.get_json()
        assert 'уже отозвана' in data['error']

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.services.application_service.postgrest_rpc')
    def test_concurrent_withdraw_only_one_succeeds(
        self, mock_rpc, mock_blacklist, worker_session
    ):
        """C2: при concurrent withdraw только один должен succeed."""
        app_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        
        # Счётчик вызовов RPC
        call_count = [0]
        
        def mock_rpc_side_effect(func_name, params, **kwargs):
            call_count[0] += 1
            # Первый вызов succeeds, второй — already_withdrawn
            if call_count[0] == 1:
                return MagicMock(
                    ok=True,
                    json=lambda: {'success': True, 'message': 'Заявка отозвана', 'new_status': 'withdrawn'}
                )
            else:
                return MagicMock(
                    ok=True,
                    json=lambda: {'success': False, 'code': 'already_withdrawn', 'error': 'Заявка уже отозвана'}
                )
        
        mock_rpc.side_effect = mock_rpc_side_effect

        def make_withdraw_request():
            return worker_session.post(
                f'/api/applications/{app_id}/withdraw',
                headers={'X-CSRF-Token': 'test-csrf-token'}
            )

        # Запускаем два параллельных запроса
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(make_withdraw_request) for _ in range(2)]
            results = [f.result() for f in as_completed(futures)]

        # Проверяем что только один succeeded
        status_codes = [r.status_code for r in results]
        assert 200 in status_codes
        assert 409 in status_codes
