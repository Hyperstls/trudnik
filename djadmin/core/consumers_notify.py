"""WS-уведомления: персональная группа user_<id> (паритет Flask notifications-ws).

Drain-задача после создания Notification шлёт её в группу пользователя;
base.html показывает toast + обновляет бейдж. Fallback — poll unread-count.
"""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return
        self.group_name = "user_%s" % user.pk
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        import json

        try:
            data = json.loads(text_data or "{}")
        except Exception:
            data = {}
        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    async def notify(self, event):
        await self.send(text_data=__import__("json").dumps({"type": "notification", **event["payload"]}))


def notify_user(user_id, payload: dict) -> None:
    """Отправить уведомление в WS-канал пользователя (null-safe)."""
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            "user_%s" % user_id, {"type": "notify", "payload": payload}
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning("ws notify_user failed", exc_info=True)
