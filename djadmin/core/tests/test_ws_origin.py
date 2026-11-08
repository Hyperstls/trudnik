"""R052: Origin-валидация WebSocket — защита от Cross-Site WebSocket Hijacking.

Прямой ASGI-харнесс вместо channels.testing (пакет тянет daphne, которого
нет в рантайме). Проверяем и саму обёртку в config.asgi (wildcard-настройки
тестов), и поведение с ограниченным ALLOWED_HOSTS на свежесобранной цепочке.
"""
import asyncio

from channels.auth import AuthMiddlewareStack
from channels.routing import URLRouter
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator
from django.test import SimpleTestCase, override_settings

from config.asgi import application
from core.routing import websocket_urlpatterns

SCOPE_BASE = {"type": "websocket", "path": "/ws/user/", "headers": [], "query_string": b""}


async def _run(app, headers):
    sent = []
    calls = {"n": 0}

    async def receive():
        # Первый вызов — websocket.connect; после close потребитель ждёт
        # websocket.disconnect, иначе ASGI-цикл не завершается.
        calls["n"] += 1
        if calls["n"] == 1:
            return {"type": "websocket.connect"}
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        sent.append(message)

    scope = dict(SCOPE_BASE, headers=list(headers))
    await app(scope, receive, send)
    return sent


def _close_code(sent):
    for message in sent:
        if message["type"] == "websocket.close":
            return message.get("code")
    return None


class WsOriginWiringTests(SimpleTestCase):
    def test_websocket_app_is_wrapped_by_origin_validator(self):
        ws_app = application.application_mapping["websocket"]
        self.assertIsInstance(ws_app, OriginValidator)

    def test_debug_wildcard_accepts_any_origin(self):
        # Тестовые настройки: ALLOWED_HOSTS=['*'] — легитимный поток не сломан:
        # валидатор пропускает, анонима закрывает сам consumer (4001).
        sent = asyncio.run(_run(application, [(b"origin", b"https://anything.test")]))
        self.assertEqual(_close_code(sent), 4001)


class WsOriginStrictTests(SimpleTestCase):
    def _strict_app(self):
        # Свежесобранная цепочка как в asgi.py; init читает override ALLOWED_HOSTS.
        return AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        )

    @override_settings(ALLOWED_HOSTS=["good.example"])
    def test_foreign_origin_denied_before_auth(self):
        sent = asyncio.run(_run(self._strict_app(), [(b"origin", b"https://evil.example")]))
        types = [m["type"] for m in sent]
        self.assertNotIn("websocket.accept", types)  # WebsocketDenier: reject до consumer
        self.assertIn("websocket.close", types)
        # код 4001 ставит только consumer (аноним) — его не было:
        self.assertNotEqual(_close_code(sent), 4001)

    @override_settings(ALLOWED_HOSTS=["good.example"])
    def test_missing_origin_denied_without_wildcard(self):
        sent = asyncio.run(_run(self._strict_app(), []))
        types = [m["type"] for m in sent]
        self.assertNotIn("websocket.accept", types)
        self.assertIn("websocket.close", types)
        self.assertNotEqual(_close_code(sent), 4001)

    @override_settings(ALLOWED_HOSTS=["good.example"])
    def test_allowed_origin_reaches_consumer(self):
        # Валидатор пропустил; анонима без accept закрывает consumer (4001).
        sent = asyncio.run(_run(self._strict_app(), [(b"origin", b"https://good.example")]))
        self.assertEqual(_close_code(sent), 4001)
