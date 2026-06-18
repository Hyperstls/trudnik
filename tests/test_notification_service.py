"""Тесты сервиса уведомлений."""
import unittest
from unittest.mock import MagicMock, patch

from app.services.notification_service import create as add_notification


class TestNotificationService(unittest.TestCase):
    """Тесты notification_service.create."""

    @patch('app.services.notification_service.redis_publisher')
    @patch('app.services.notification_service.get_user_prefs')
    @patch('app.services.notification_service.supabase_admin_request')
    def test_create_notification_success(self, mock_admin, mock_prefs, mock_redis):
        """Уведомление создаётся и публикуется."""
        mock_admin.return_value = MagicMock(ok=True, json=lambda: [{'id': 'notif-1'}])
        mock_prefs.return_value = {'test': True}
        result = add_notification(
            user_id='user-1', notification_type='test',
            title='Тест', message='Тестовое уведомление',
        )
        self.assertTrue(result)
        mock_admin.assert_called_once()
        call_args = mock_admin.call_args
        self.assertEqual(call_args[0][0], 'POST')
        self.assertEqual(call_args[0][1], 'notifications')
        payload = call_args[1]['json']
        self.assertEqual(payload['user_id'], 'user-1')
        self.assertEqual(payload['type'], 'test')
        self.assertEqual(payload['message'], 'Тест: Тестовое уведомление')
        self.assertEqual(payload['is_read'], False)

    @patch('app.services.notification_service.get_user_prefs')
    def test_create_notification_unknown_type(self, mock_prefs):
        """Неизвестный тип уведомления — возвращает False."""
        result = add_notification(
            user_id='user-1', notification_type='nonexistent',
            title='X', message='Y',
        )
        self.assertFalse(result)
        mock_prefs.assert_not_called()

    @patch('app.services.notification_service.get_user_prefs')
    @patch('app.services.notification_service.supabase_admin_request')
    def test_create_notification_disabled_by_prefs(self, mock_admin, mock_prefs):
        """Уведомление отключено в настройках — не создаётся."""
        mock_prefs.return_value = {'test': False}
        result = add_notification(
            user_id='user-1', notification_type='test',
            title='Тест', message='Тестовое уведомление',
        )
        self.assertFalse(result)
        mock_admin.assert_not_called()


if __name__ == '__main__':
    unittest.main()
