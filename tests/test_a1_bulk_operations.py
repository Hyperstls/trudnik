"""
A1: Bulk-операции через атомарные RPC

Тесты проверяют, что bulk-операции (cancel/restore/delete) используют
атомарные RPC функции вместо прямых PATCH запросов.
"""
import pytest
from unittest.mock import patch, MagicMock
from flask import session


@pytest.fixture
def employer_session(app_client):
    """Сессия авторизованного работодателя."""
    with app_client.session_transaction() as sess:
        sess['user_id'] = '11111111-1111-1111-1111-111111111111'
        sess['role'] = 'employer'
        sess['_csrf_token'] = 'test-csrf-token'
    return app_client


class TestBulkCancelUsesAtomicRPC:
    """Тесты для bulk-cancel операции."""

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_cancel_calls_cancel_job_atomic_rpc(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A1: bulk-cancel должен вызывать cancel_job_atomic RPC."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True, 'new_status': 'cancelled'}
        )

        job_ids = [
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        ]

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'cancel',
                'job_ids': job_ids
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что RPC был вызван для каждого job_id
        assert mock_rpc.call_count == 2
        
        # Проверяем что вызван именно cancel_job_atomic
        for call in mock_rpc.call_args_list:
            args, kwargs = call
            assert args[0] == 'cancel_job_atomic'
            assert 'p_job_id' in args[1]
            assert 'p_user_id' in args[1]

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_cancel_returns_409_for_accepted_workers(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A1: bulk-cancel должен возвращать ошибку при наличии accepted workers."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {
                'success': False,
                'code': 'has_accepted_workers',
                'error': 'Невозможно отменить задание с принятыми работниками'
            }
        )

        job_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'cancel',
                'job_ids': [job_id]
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что было flash сообщение об ошибке
        with employer_session.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            assert any('принятые работники' in msg for cat, msg in flashes)


class TestBulkRestoreUsesAtomicRPC:
    """Тесты для bulk-restore операции."""

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_restore_calls_restore_job_atomic_rpc(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A1: bulk-restore должен вызывать restore_job_atomic RPC."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True, 'job_status': 'open'}
        )

        job_ids = ['dddddddd-dddd-dddd-dddd-dddddddddddd']

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'restore',
                'job_ids': job_ids
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что RPC был вызван
        assert mock_rpc.call_count == 1
        args, kwargs = mock_rpc.call_args
        assert args[0] == 'restore_job_atomic'
        assert 'p_job_id' in args[1]
        assert 'p_user_id' in args[1]


class TestBulkDeleteUsesCascadeRPC:
    """Тесты для bulk-delete операции."""

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_delete_calls_delete_job_cascade_rpc(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A1: bulk-delete должен вызывать delete_job_cascade RPC."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True}
        )

        job_ids = ['eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee']

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'delete',
                'job_ids': job_ids
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что RPC был вызван
        assert mock_rpc.call_count == 1
        args, kwargs = mock_rpc.call_args
        assert args[0] == 'delete_job_cascade'
        assert 'p_job_id' in args[1]


class TestBulkOperationsErrorHandling:
    """Тесты для обработки ошибок в bulk-операциях."""

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_operation_skips_non_owned_jobs(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A1: bulk-операция должна пропускать задания, не принадлежащие пользователю."""
        # Первое задание принадлежит, второе - нет
        mock_check_owner.side_effect = [True, False]
        mock_rpc.return_value = MagicMock(
            ok=True,
            json=lambda: {'success': True}
        )

        job_ids = [
            'ffffffff-ffff-ffff-ffff-ffffffffffff',
            '00000000-0000-0000-0000-000000000000'
        ]

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'cancel',
                'job_ids': job_ids
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # RPC должен быть вызван только для первого задания
        assert mock_rpc.call_count == 1

    @patch('app.blueprints.jobs.postgrest_rpc')
    @patch('app.blueprints.jobs.check_job_owner')
    def test_bulk_operation_handles_rpc_failure(
        self, mock_check_owner, mock_rpc, employer_session
    ):
        """A1: bulk-операция должна обрабатывать ошибки RPC."""
        mock_check_owner.return_value = True
        mock_rpc.return_value = MagicMock(
            ok=False,
            status_code=500
        )

        job_ids = ['11111111-1111-1111-1111-111111111111']

        response = employer_session.post(
            '/my-jobs/action',
            data={
                'action': 'cancel',
                'job_ids': job_ids
            },
            headers={'X-CSRF-Token': 'test-csrf-token'}
        )

        # Проверяем что было flash сообщение об ошибке
        with employer_session.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            assert any('Ошибка' in msg for cat, msg in flashes)
