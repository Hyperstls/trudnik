"""
Redis Publisher — синхронный клиент для публикации событий из Flask-приложения.
"""
import json
import os
import logging
import redis

logger = logging.getLogger(__name__)


class RedisPublisher:
    """Публикует события в Redis Pub/Sub из синхронного Flask-контекста."""

    _instance = None

    def __init__(self):
        self.redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        self._client = None

    def _get_client(self):
        """Ленивое подключение к Redis."""
        if self._client is None:
            try:
                self._client = redis.from_url(self.redis_url, decode_responses=True)
                self._client.ping()
                logger.info("Redis Publisher подключён к %s", self.redis_url)
            except redis.ConnectionError as e:
                logger.warning("Redis недоступен (%s). События не будут публиковаться.", e)
                self._client = None
        return self._client

    def publish(self, channel: str, message: dict) -> bool:
        """
        Публикует сообщение в Redis канал.

        Args:
            channel: имя канала ('notifications' или 'chat')
            message: словарь с данными события

        Returns:
            True если опубликовано успешно, False при ошибке
        """
        client = self._get_client()
        if client is None:
            return False

        try:
            payload = json.dumps(message, ensure_ascii=False, default=str)
            client.publish(channel, payload)
            logger.debug("Опубликовано в канал '%s': %s", channel, message.get('type'))
            return True
        except Exception as e:
            logger.error("Ошибка публикации в Redis канал '%s': %s", channel, e)
            return False

    def publish_notification(self, user_id: int, notification_type: str, data: dict) -> bool:
        """Публикует событие уведомления для конкретного пользователя."""
        return self.publish('notifications', {
            'type': 'notification',
            'notification_type': notification_type,
            'user_id': user_id,
            'data': data,
            'timestamp': None  # Будет заполнено на стороне WebSocket-сервера
        })

    def publish_chat_message(self, sender_id: int, recipient_id: int, message_data: dict) -> bool:
        """Публикует событие нового сообщения чата."""
        # Публикуем для получателя
        result1 = self.publish('chat', {
            'type': 'new_message',
            'user_id': recipient_id,
            'sender_id': sender_id,
            'data': message_data
        })
        # И для отправителя (чтобы обновить UI на других вкладках)
        result2 = self.publish('chat', {
            'type': 'new_message',
            'user_id': sender_id,
            'sender_id': sender_id,
            'data': message_data
        })
        return result1 or result2

    def close(self):
        """Закрывает соединение с Redis."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


# Глобальный экземпляр (синглтон)
redis_publisher = RedisPublisher()
