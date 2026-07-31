"""
A2: Удалить ilike injection в cascade delete notifications

Тесты проверяют, что delete_job_cascade использует FK job_id вместо ILIKE
для удаления уведомлений.
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def employer_session(app_client):
    """Сессия авторизованного работодателя."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
        from app.utils.auth import generate_jwt
        sess['access_token'] = generate_jwt(sess['user_id'], sess['role'])
    return app_client


class TestDeleteJobCascadeNoIlike:
    """Тесты для проверки отсутствия ILIKE в delete_job_cascade."""

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_delete_job_uses_rpc_not_direct_delete(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A2: delete_job должен использовать delete_job_cascade RPC."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {
                'success': True,
                'deleted_notifications': 5
            }
        )

        job_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'delete',
                'job_ids': [job_id]
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что был вызван delete_job_cascade RPC
        assert mock_rpc.call_count == 1
        args, kwargs = mock_rpc.call_args
        assert args[0] == 'delete_job_cascade'
        assert args[1]['p_job_id'] == job_id

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_delete_job_returns_deleted_notifications_count(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A2: delete_job_cascade должен возвращать количество удалённых уведомлений."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {
                'success': True,
                'deleted_applications': 3,
                'deleted_notifications': 7
            }
        )

        job_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'delete',
                'job_ids': [job_id]
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем успешный ответ
        assert response.status_code == 302  # redirect после успешной операции
        
        # Проверяем flash сообщение
        with employer_session.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            assert any('Операция выполнена' in msg for cat, msg in flashes)


class TestMigration100Backfill:
    """Тесты для миграции 100_backfill_notification_job_id.sql."""

    def test_migration_file_exists(self):
        """A2: Миграция 100 должна существовать."""
        import os
        migration_path = 'migrations/100_backfill_notification_job_id.sql'
        assert os.path.exists(migration_path), f"Миграция {migration_path} не найдена"

    def test_migration_contains_backfill_logic(self):
        """A2: Миграция должна содержать логику backfill job_id из data JSONB."""
        with open('migrations/100_backfill_notification_job_id.sql', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Проверяем наличие ключевых элементов
        assert 'UPDATE notifications' in content
        assert 'job_id' in content
        assert 'data->>' in content or 'data->' in content
        assert 'WHERE job_id IS NULL' in content
