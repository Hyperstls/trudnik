"""WebSocket-чат: комнаты по заявке (паритет chat_access — только участники).

Приём сообщений идёт через HTTP POST /chat/<id>/send (CSRF + идемпотентность
client_message_id сохранены), а WebSocket — «шина» доставки: сервер шлёт
новые сообщения всем участникам комнаты. Fallback — HTTP-poll 5с (chat.html).
"""
import json
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return
        app_id = self.scope["url_route"]["kwargs"]["app_id"]
        allowed = await database_sync_to_async(self._is_participant)(app_id, user.pk)
        if not allowed:
            await self.close(code=4003)
            return
        self.group_name = "chat_%s" % app_id
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        """Зарезервировано: сообщения принимаем по HTTP (CSRF+идемпотентность)."""
        try:
            data = json.loads(text_data or "{}")
        except Exception:
            data = {}
        if data.get("type") == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({"type": "message", **event["payload"]}))

    # ── синхронные хелперы (database_sync_to_async) ────────────────────
    @staticmethod
    def _is_participant(app_id, user_id) -> bool:
        from .models import Application

        app = Application.objects.select_related("job").filter(pk=app_id).first()
        if app is None:
            return False
        return user_id in (app.worker_id, app.job.employer_id)


def notify_new_message(application_id, message: dict) -> None:
    """Отправить сообщение в комнату из синхронного кода (view chat_send).

    Null-safe: без Redis/каналов просто ничего не делает (poll всё покажет).
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            "chat_%s" % application_id,
            {"type": "chat_message", "payload": message},
        )
    except Exception:
        import logging

        logging.getLogger(__name__).warning("chat ws notify failed", exc_info=True)
