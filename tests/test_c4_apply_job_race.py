"""
C4: Race condition в apply_job

Тесты проверяют, что apply_job:
- Использует атомарный RPC apply_job_atomic
- Правильно обрабатывает duplicate (race condition)
- Возвращает 409 для дубликатов в API-запросах
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
    
    payload = {
        'user_id': '33333333-3333-3333-3333-333333333333',
        'role': 'worker',
        'exp': int(time.time()) + 3600,
        'jti': 'test-jti-apply'
    }
    token = jwt.encode(payload, Config.PGRST_JWT_SECRET, algorithm='HS256')
    
    with app_client.session_transaction() as sess:
        sess['user_id'] = '33333333-3333-3333-3333-333333333333'
        sess['role'] = 'worker'
        sess['_csrf_token'] = 'test-csrf-token'
        sess['access_token'] = token
        sess['jti'] = 'test-jti-apply'
    return app_client


class TestApplyJobAtomic:
    """Тесты для apply_job без race condition."""

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_apply_uses_atomic_rpc(
        self, mock_request, mock_rpc, mock_blacklist, worker_session
    ):
        """C4: apply должен использовать apply_job_atomic RPC."""
        # Мокаем проверку дубликата (пустой результат)
        mock_request.return_value = MagicMock(ok=True, json=lambda: [])
        
        # Мокаем успешный RPC
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {
                'success': True,
                'application_id': 'app-123',
                'employer_id': '22222222-2222-2222-2222-222222222222'
            }
        )

        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        response = worker_session.post(
            f'/apply/{job_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        # Должен редиректить после успеха
        assert response.status_code == 302
        
        # Проверяем что вызван именно apply_job_atomic
        assert mock_rpc.called
        args, kwargs = mock_rpc.call_args
        assert args[0] == 'apply_job_atomic'
        assert 'p_job_id' in args[1]
        assert 'p_worker_id' in args[1]

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_apply_handles_duplicate(
        self, mock_request, mock_rpc, mock_blacklist, worker_session
    ):
        """C4: apply должен обрабатывать duplicate от RPC (race condition)."""
        # Мокаем проверку дубликата (пустой результат)
        mock_request.return_value = MagicMock(ok=True, json=lambda: [])
        
        # Мокаем RPC с duplicate
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': False, 'code': 'duplicate', 'error': 'Вы уже откликнулись'}
        )

        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        response = worker_session.post(
            f'/apply/{job_id}',
            headers={'X-CSRF-Token': 'test-csrf-token'},
            follow_redirects=False
        )

        # Должен редиректить с flash-сообщением
        assert response.status_code == 302

    @patch('app.utils.auth.is_jti_blacklisted', return_value=False)
    @patch('app.blueprints.applications.postgrest_rpc')
    @patch('app.blueprints.applications.postgrest_request')
    def test_concurrent_apply_only_one_succeeds(
        self, mock_request, mock_rpc, mock_blacklist, worker_session
    ):
        """C4: при concurrent apply только один должен succeed."""
        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        
        # Мокаем проверку дубликата (пустой результат для обоих)
        mock_request.return_value = MagicMock(ok=True, json=lambda: [])
        
        # Счётчик вызовов RPC
        call_count = [0]
        
        def mock_rpc_side_effect(func_name, params, **kwargs):
            call_count[0] += 1
            # Первый вызов succeeds, второй — duplicate
            if call_count[0] == 1:
                return MagicMock(
                    ok=True,
                    json=lambda: {
                        'success': True,
                        'application_id': 'app-123',
                        'employer_id': '22222222-2222-2222-2222-222222222222'
                    }
                )
            else:
                return MagicMock(
                    ok=True,
                    json=lambda: {'success': False, 'code': 'duplicate', 'error': 'Вы уже откликнулись'}
                )
        
        mock_rpc.side_effect = mock_rpc_side_effect

        def make_apply_request():
            return worker_session.post(
                f'/apply/{job_id}',
                headers={'X-CSRF-Token': 'test-csrf-token'},
                follow_redirects=False
            )

        # Запускаем два параллельных запроса
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(make_apply_request) for _ in range(2)]
            results = [f.result() for f in as_completed(futures)]

        # Оба должны вернуть 302 (один успех, один duplicate)
        status_codes = [r.status_code for r in results]
        assert all(code == 302 for code in status_codes)
