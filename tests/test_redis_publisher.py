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
        # Создаём новый экземпляр для каждого теста
        self.publisher = RedisPublisher()
        # Сбрасываем внутреннего клиента
        self.publisher._client = None

    def tearDown(self) -> None:
        """Закрываем соединение после каждого теста."""
        self.publisher.close()

    # ────────────────────────────────────────────────────────────
    # Публикация сообщений
    # ────────────────────────────────────────────────────────────

    @patch('redis.from_url')
    def test_publish_success(self, mock_from_url: MagicMock) -> None:
        """Успешная публикация сообщения в Redis канал."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        result = self.publisher.publish(
            'notifications',
            {'type': 'notification', 'user_id': 1, 'data': {'text': 'Привет'}},
        )

        self.assertTrue(result)
        mock_client.publish.assert_called_once()
        # Проверяем, что в канал опубликована JSON-строка
        call_args = mock_client.publish.call_args
        self.assertEqual(call_args[0][0], 'notifications')

    def test_publish_redis_unavailable(self) -> None:
        """Redis недоступен — publish возвращает False, не падает."""
        # Мокируем _get_client чтобы симулировать недоступность Redis
        self.publisher._get_client = MagicMock(return_value=None)

        result = self.publisher.publish(
            'notifications',
            {'type': 'test'},
        )

        self.assertFalse(result)

    @patch('redis.from_url')
    def test_publish_notification(self, mock_from_url: MagicMock) -> None:
        """Публикация уведомления через publish_notification."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        result = self.publisher.publish_notification(
            user_id=42,
            notification_type='new_job',
            data={'job_id': 'abc-123', 'title': 'Новая вакансия'},
        )

        self.assertTrue(result)
        mock_client.publish.assert_called_once()

        # Проверяем структуру опубликованного сообщения
        import json
        args, _ = mock_client.publish.call_args
        payload = json.loads(args[1])
        self.assertEqual(payload['type'], 'notification')
        self.assertEqual(payload['notification_type'], 'new_job')
        self.assertEqual(payload['user_id'], 42)
        self.assertEqual(payload['data']['job_id'], 'abc-123')

    @patch('redis.from_url')
    def test_publish_chat_message(self, mock_from_url: MagicMock) -> None:
        """Публикация сообщения чата через publish_chat_message."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        result = self.publisher.publish_chat_message(
            sender_id=10,
            recipient_id=20,
            message_data={'text': 'Привет!', 'id': 'msg-001'},
        )

        self.assertTrue(result)
        # Должно быть 2 вызова publish: для получателя и отправителя
        self.assertEqual(mock_client.publish.call_count, 2)

    @patch('redis.from_url')
    def test_publish_encoding(self, mock_from_url: MagicMock) -> None:
        """Публикация сообщения с Unicode-символами (русский текст)."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        result = self.publisher.publish(
            'notifications',
            {'type': 'notification', 'text': 'Привет, мир! 👍'},
        )

        self.assertTrue(result)
        # Проверяем, что JSON содержит кириллицу корректно
        import json
        args, _ = mock_client.publish.call_args
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

    @patch('redis.from_url')
    def test_close_cleans_up_client(self, mock_from_url: MagicMock) -> None:
        """Закрытие соединения очищает внутреннего клиента."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        # Инициализируем клиент через publish
        self.publisher.publish('test', {'type': 'test'})
        self.assertIsNotNone(self.publisher._client)

        # Закрываем
        self.publisher.close()
        self.assertIsNone(self.publisher._client)
        mock_client.close.assert_called_once()

    @patch('redis.from_url')
    def test_close_handles_exception(self, mock_from_url: MagicMock) -> None:
        """Закрытие не падает, даже если клиент бросает исключение."""
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("Close failed")
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        self.publisher.publish('test', {'type': 'test'})

        # Не должно падать
        self.publisher.close()
        self.assertIsNone(self.publisher._client)


if __name__ == '__main__':
    unittest.main()
