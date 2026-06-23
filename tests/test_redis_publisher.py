"""Тесты для RedisPublisher — публикация событий в Redis Pub/Sub."""

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.redis_publisher import RedisPublisher


class TestRedisPublisher(unittest.TestCase):
    """Unit-тесты Redis Publisher."""

    def setUp(self) -> None:
        """Установка тестовых переменных окружения."""
        os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
        self.publisher = RedisPublisher()
        self.publisher._client = None

    def tearDown(self) -> None:
        """Закрываем соединение после каждого теста."""
        self.publisher.close()

    # ────────────────────────────────────────────────────────────
    # Публикация сообщений
    # ────────────────────────────────────────────────────────────

    def test_publish_success(self) -> None:
        """Успешная публикация сообщения в Redis канал."""
        result = self.publisher.publish(
            'notifications',
            {'type': 'notification', 'user_id': 1, 'data': {'text': 'Привет'}},
        )

        self.assertTrue(result)
        self.assertIsNotNone(self.publisher._client)
        self.publisher._client.publish.assert_called_once()
        call_args = self.publisher._client.publish.call_args
        self.assertEqual(call_args[0][0], 'notifications')

    def test_publish_redis_unavailable(self) -> None:
        """Redis недоступен — publish возвращает False, не падает."""
        self.publisher._get_client = MagicMock(return_value=None)

        result = self.publisher.publish(
            'notifications',
            {'type': 'test'},
        )

        self.assertFalse(result)

    def test_publish_notification(self) -> None:
        """Публикация уведомления через publish_notification."""
        result = self.publisher.publish_notification(
            user_id=42,
            notification_type='new_job',
            data={'job_id': 'abc-123', 'title': 'Новая вакансия'},
        )

        self.assertTrue(result)
        self.publisher._client.publish.assert_called_once()

        import json
        args, _ = self.publisher._client.publish.call_args
        payload = json.loads(args[1])
        self.assertEqual(payload['type'], 'notification')
        self.assertEqual(payload['notification_type'], 'new_job')
        self.assertEqual(payload['user_id'], 42)
        self.assertEqual(payload['data']['job_id'], 'abc-123')

    def test_publish_chat_message(self) -> None:
        """Публикация сообщения чата через publish_chat_message."""
        result = self.publisher.publish_chat_message(
            sender_id=10,
            recipient_id=20,
            message_data={'text': 'Привет!', 'id': 'msg-001'},
        )

        self.assertTrue(result)
        self.assertEqual(self.publisher._client.publish.call_count, 2)

    def test_publish_encoding(self) -> None:
        """Публикация сообщения с Unicode-символами (русский текст)."""
        result = self.publisher.publish(
            'notifications',
            {'type': 'notification', 'text': 'Привет, мир! 👍'},
        )

        self.assertTrue(result)
        import json
        args, _ = self.publisher._client.publish.call_args
        payload = json.loads(args[1])
        self.assertIn('Привет, мир!', payload['text'])

    # ────────────────────────────────────────────────────────────
    # Синглтон
    # ────────────────────────────────────────────────────────────

    def test_singleton_instance_exists(self) -> None:
        """Глобальный экземпляр redis_publisher существует и является RedisPublisher."""
        from app.services.redis_publisher import redis_publisher

        self.assertIsInstance(redis_publisher, RedisPublisher)

    # ────────────────────────────────────────────────────────────
    # Закрытие соединения
    # ────────────────────────────────────────────────────────────

    def test_close_cleans_up_client(self) -> None:
        """Закрытие соединения очищает внутреннего клиента."""
        self.publisher.publish('test', {'type': 'test'})
        self.assertIsNotNone(self.publisher._client)
        client_before_close = self.publisher._client

        self.publisher.close()
        self.assertIsNone(self.publisher._client)
        client_before_close.close.assert_called_once()

    def test_close_handles_exception(self) -> None:
        """Закрытие не падает, даже если клиент бросает исключение."""
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("Close failed")
        mock_client.ping.return_value = True
        self.publisher._get_client = MagicMock(return_value=mock_client)

        self.publisher.publish('test', {'type': 'test'})
        self.publisher.close()
        self.assertIsNone(self.publisher._client)


if __name__ == '__main__':
    unittest.main()
