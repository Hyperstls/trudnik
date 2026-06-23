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
        # Первый вызов: POST notifications → возвращает созданное уведомление
        # Второй вызов: GET profiles → возвращает email/username для Celery
        mock_admin.side_effect = [
            MagicMock(ok=True, json=lambda: [{'id': 'notif-1'}]),
            MagicMock(ok=True, json=lambda: [{'email': 'test@test.ru', 'username': 'Тестер'}])
        ]
        mock_prefs.return_value = {'status_change': True}
        result = add_notification(
            user_id='user-1', notification_type='status_change',
            title='Тест', message='Тестовое уведомление',
        )
        self.assertTrue(result)
        # Проверяем первый вызов — POST notifications
        first_call = mock_admin.call_args_list[0]
        self.assertEqual(first_call[0][0], 'POST')
        self.assertEqual(first_call[0][1], 'notifications')
        payload = first_call[1]['json']
        self.assertEqual(payload['user_id'], 'user-1')
        self.assertEqual(payload['type'], 'status_change')
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
        mock_prefs.return_value = {'status_change': False}
        result = add_notification(
            user_id='user-1', notification_type='status_change',
            title='Тест', message='Тестовое уведомление',
        )
        self.assertFalse(result)
        mock_admin.assert_not_called()


if __name__ == '__main__':
    unittest.main()
