"""Тесты для PushService — Web Push уведомления, VAPID-ключи, отправка через pywebpush."""

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.push_service import PushService


class TestPushService(unittest.TestCase):
    """Unit-тесты сервиса Push-уведомлений."""

    def setUp(self) -> None:
        """Установка тестовых переменных окружения."""
        os.environ['VAPID_PRIVATE_KEY'] = 'test-private-key-base64url'
        os.environ['VAPID_PUBLIC_KEY'] = 'test-public-key-base64url'
        os.environ['VAPID_CLAIMS_EMAIL'] = 'notifications@trudnik.ru'
        os.environ['VAPID_CLAIMS_SUBJECT'] = 'mailto:notifications@trudnik.ru'
        self.service = PushService()

    # ────────────────────────────────────────────────────────────
    # Генерация VAPID-ключей
    # ────────────────────────────────────────────────────────────

    def test_generate_vapid_keys(self) -> None:
        """Генерация VAPID-ключей возвращает кортеж (private, public) в base64url."""
        private_key, public_key = PushService.generate_vapid_keys()

        self.assertIsInstance(private_key, str)
        self.assertIsInstance(public_key, str)
        self.assertTrue(len(private_key) > 0)
        self.assertTrue(len(public_key) > 0)
        # base64url без padding: только A-Za-z0-9-_ символы
        self.assertTrue(all(c.isalnum() or c in '-_' for c in private_key))
        self.assertTrue(all(c.isalnum() or c in '-_' for c in public_key))
        # Ключи должны различаться
        self.assertNotEqual(private_key, public_key)

    def test_generate_vapid_keys_format(self) -> None:
        """VAPID-ключи не содержат padding-символов '='."""
        private_key, public_key = PushService.generate_vapid_keys()

        self.assertNotIn('=', private_key)
        self.assertNotIn('=', public_key)

    # ────────────────────────────────────────────────────────────
    # Отправка уведомления
    # ────────────────────────────────────────────────────────────

    @patch('pywebpush.WebPusher')
    def test_send_notification_success(self, mock_webpusher: MagicMock) -> None:
        """Успешная отправка push-уведомления через pywebpush."""
        mock_pusher_instance = MagicMock()
        mock_webpusher.return_value = mock_pusher_instance

        subscription_info = {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/test-endpoint',
            'p256dh': 'BP_test_p256dh_key_base64url',
            'auth': 'test_auth_secret_base64url',
        }
        payload = {
            'title': 'Тестовое уведомление',
            'body': 'Текст уведомления',
            'url': '/jobs/test-job-id',
        }

        result = self.service.send_notification(subscription_info, payload)

        self.assertTrue(result['success'])
        self.assertIsNone(result['error'])
        self.assertFalse(result['should_unsubscribe'])
        mock_pusher_instance.send.assert_called_once()

    @patch('pywebpush.WebPusher')
    def test_send_notification_without_vapid_keys(self, mock_webpusher: MagicMock) -> None:
        """Отправка без VAPID-ключей — возвращает ошибку конфигурации."""
        os.environ['VAPID_PRIVATE_KEY'] = ''
        os.environ['VAPID_PUBLIC_KEY'] = ''
        service = PushService()

        result = service.send_notification(
            {'endpoint': 'https://example.com/push', 'p256dh': 'key', 'auth': 'auth'},
            {'title': 'Test'},
        )

        self.assertFalse(result['success'])
        self.assertIn('VAPID', result['error'])

    @patch('pywebpush.WebPusher')
    def test_send_notification_gone(self, mock_webpusher: MagicMock) -> None:
        """Обработка 410 Gone — подписка недействительна, should_unsubscribe=True."""
        from pywebpush import WebPushException

        # Создаём mock-ответ с status_code 410
        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_pusher_instance = MagicMock()
        mock_pusher_instance.send.side_effect = WebPushException(
            "Subscription gone", response=mock_response
        )
        mock_webpusher.return_value = mock_pusher_instance

        result = self.service.send_notification(
            {
                'endpoint': 'https://example.com/push',
                'p256dh': 'key',
                'auth': 'auth',
            },
            {'title': 'Test'},
        )

        self.assertFalse(result['success'])
        self.assertTrue(result['should_unsubscribe'])
        self.assertIn('410', result['error'])

    @patch('pywebpush.WebPusher')
    def test_send_notification_generic_error(self, mock_webpusher: MagicMock) -> None:
        """Общая ошибка при отправке — success=False, should_unsubscribe=False."""
        mock_pusher_instance = MagicMock()
        mock_pusher_instance.send.side_effect = Exception("Unexpected network error")
        mock_webpusher.return_value = mock_pusher_instance

        result = self.service.send_notification(
            {
                'endpoint': 'https://example.com/push',
                'p256dh': 'key',
                'auth': 'auth',
            },
            {'title': 'Test'},
        )

        self.assertFalse(result['success'])
        self.assertFalse(result['should_unsubscribe'])
        self.assertIn('Unexpected network error', result['error'])

    # ────────────────────────────────────────────────────────────
    # Управление подписками (мокируем Supabase REST API)
    # ────────────────────────────────────────────────────────────

    @patch('app.services.push_service.postgrest_admin_request')
    def test_save_subscription_new(self, mock_postgrest: MagicMock) -> None:
        """Сохранение новой push-подписки пользователя."""
        # Эмулируем: проверка существующей подписки — пустой ответ
        mock_check_response = MagicMock()
        mock_check_response.ok = True
        mock_check_response.json.return_value = []

        # Эмулируем: создание новой подписки — успех
        mock_create_response = MagicMock()
        mock_create_response.ok = True

        mock_postgrest.side_effect = [mock_check_response, mock_create_response]

        result = self.service.save_subscription(
            user_id='user-uuid-123',
            subscription_data={
                'endpoint': 'https://example.com/push/endpoint',
                'keys': {
                    'p256dh': 'test-p256dh-key',
                    'auth': 'test-auth-secret',
                },
            },
        )

        self.assertTrue(result)

    @patch('app.services.push_service.postgrest_admin_request')
    def test_save_subscription_missing_endpoint(self, mock_postgrest: MagicMock) -> None:
        """Сохранение подписки без endpoint — возвращает False."""
        result = self.service.save_subscription(
            user_id='user-uuid-123',
            subscription_data={'endpoint': '', 'keys': {}},
        )

        self.assertFalse(result)
        mock_postgrest.assert_not_called()

    @patch('app.services.push_service.postgrest_admin_request')
    def test_delete_subscription(self, mock_postgrest: MagicMock) -> None:
        """Удаление push-подписки по endpoint."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_postgrest.return_value = mock_response

        result = self.service.delete_subscription('https://example.com/push/endpoint')

        self.assertTrue(result)

    @patch('app.services.push_service.postgrest_admin_request')
    def test_delete_subscription_empty_endpoint(self, mock_postgrest: MagicMock) -> None:
        """Удаление с пустым endpoint — возвращает False."""
        result = self.service.delete_subscription('')

        self.assertFalse(result)
        mock_postgrest.assert_not_called()


if __name__ == '__main__':
    unittest.main()
