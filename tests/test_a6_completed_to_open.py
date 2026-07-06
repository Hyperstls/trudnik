"""
A6: Запрет перехода completed→open с orphan ratings

Тесты проверяют, что admin не может перевести вакансию из completed
обратно в open при наличии существующих ratings.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def admin_session(client):
    """Сессия авторизованного администратора."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'admin-admin-admin-admin-adminadminadmin'
        sess['role'] = 'admin'
        sess['_csrf_token'] = 'test-csrf-token'
    return client


class TestCompletedToOpenWithRatings:
    """Тесты для запрета перехода completed→open с ratings."""

    @patch('app.blueprints.admin_jobs.log_admin_action')
    @patch('app.blueprints.admin_jobs.postgrest_admin_request')
    def test_completed_to_open_blocked_with_ratings(
        self, mock_postgrest, mock_log, admin_session
    ):
        """A6: переход completed→open должен быть заблокирован при наличии ratings."""
        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        
        # Mock: первый запрос - получение текущего статуса (completed)
        # Mock: второй запрос - проверка ratings (есть ratings)
        def side_effect(method, url, **kwargs):
            if 'jobs?id=eq' in url and method == 'GET':
                return MagicMock(
                    ok=True,
                    json=lambda: [{'status': 'completed'}]
                )
            elif 'ratings?job_id=eq' in url and method == 'GET':
                return MagicMock(
                    ok=True,
                    json=lambda: [{'id': 'rating-1'}]  # Есть ratings
                )
            return MagicMock(ok=True, json=lambda: [])
        
        mock_postgrest.side_effect = side_effect

        response = admin_session.post(
            f'/admin/jobs/{job_id}/status',
            data={'status': 'open'},
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что было flash сообщение об ошибке
        with admin_session.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            assert any('оценками' in msg for cat, msg in flashes)

    @patch('app.blueprints.admin_jobs.log_admin_action')
    @patch('app.blueprints.admin_jobs.postgrest_admin_request')
    def test_completed_to_open_allowed_without_ratings(
        self, mock_postgrest, mock_log, admin_session
    ):
        """A6: переход completed→open должен быть разрешён без ratings."""
        job_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        
        # Mock: первый запрос - получение текущего статуса (completed)
        # Mock: второй запрос - проверка ratings (нет ratings)
        # Mock: третий запрос - PATCH для изменения статуса
        def side_effect(method, url, **kwargs):
            if 'jobs?id=eq' in url and method == 'GET':
                return MagicMock(
                    ok=True,
                    json=lambda: [{'status': 'completed'}]
                )
            elif 'ratings?job_id=eq' in url and method == 'GET':
                return MagicMock(
                    ok=True,
                    json=lambda: []  # Нет ratings
                )
            elif method == 'PATCH':
                return MagicMock(ok=True, status_code=200)
            return MagicMock(ok=True, json=lambda: [])
        
        mock_postgrest.side_effect = side_effect

        response = admin_session.post(
            f'/admin/jobs/{job_id}/status',
            data={'status': 'open'},
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что было flash сообщение об успехе
        with admin_session.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            assert any('изменён на open' in msg for cat, msg in flashes)

    @patch('app.blueprints.admin_jobs.log_admin_action')
    @patch('app.blueprints.admin_jobs.postgrest_admin_request')
    def test_open_to_completed_always_allowed(
        self, mock_postgrest, mock_log, admin_session
    ):
        """A6: переход open→completed должен быть всегда разрешён."""
        job_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
        
        # Mock: первый запрос - получение текущего статуса (open)
        # Mock: второй запрос - PATCH для изменения статуса
        def side_effect(method, url, **kwargs):
            if 'jobs?id=eq' in url and method == 'GET':
                return MagicMock(
                    ok=True,
                    json=lambda: [{'status': 'open'}]
                )
            elif method == 'PATCH':
                return MagicMock(ok=True, status_code=200)
            return MagicMock(ok=True, json=lambda: [])
        
        mock_postgrest.side_effect = side_effect

        response = admin_session.post(
            f'/admin/jobs/{job_id}/status',
            data={'status': 'completed'},
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что было flash сообщение об успехе
        with admin_session.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            assert any('изменён на completed' in msg for cat, msg in flashes)
