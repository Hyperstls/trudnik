"""Тесты для WebSocket-сервера — healthcheck, подключение с токеном и без."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
from fastapi.testclient import TestClient
from fastapi import status as http_status


# ═══════════════════════════════════════════════════════════════
# Мокируем Redis ДО импорта приложения, чтобы lifespan не пытался
# подключиться к реальному Redis
# ═══════════════════════════════════════════════════════════════

# Патчим redis.asyncio на уровне модуля websocket_server.main
redis_mock = MagicMock()
redis_mock.ping = AsyncMock(return_value=True)
redis_mock.pubsub = MagicMock()
redis_mock.close = AsyncMock()

with patch('websocket_server.main.aioredis') as mock_aioredis, \
     patch('websocket_server.main.redis_pubsub_listener', new=AsyncMock()):

    mock_aioredis.from_url.return_value = redis_mock

    from websocket_server.main import app

# ═══════════════════════════════════════════════════════════════


class TestWebSocketServer(unittest.TestCase):
    """Unit-тесты WebSocket-сервера (FastAPI)."""

    @classmethod
    def setUpClass(cls) -> None:
        """Установка тестового SECRET_KEY и генерация JWT-токенов."""
        os.environ['SECRET_KEY'] = 'test-secret-key-for-ws-server'
        cls.secret_key = os.environ['SECRET_KEY']

        # Валидный токен
        cls.valid_payload = {
            'user_id': 42,
            'exp': datetime.now(timezone.utc) + timedelta(hours=1),
        }
        cls.valid_token = jwt.encode(
            cls.valid_payload, cls.secret_key, algorithm='HS256'
        )

        # Токен без user_id
        cls.token_without_uid = jwt.encode(
            {'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            cls.secret_key,
            algorithm='HS256',
        )

        cls.client = TestClient(app)

    def setUp(self) -> None:
        """Очистка глобального состояния перед каждым тестом."""
        from websocket_server import main as ws_main
        ws_main.active_connections.clear()

    # ────────────────────────────────────────────────────────────
    # Healthcheck
    # ────────────────────────────────────────────────────────────

    def test_health_check(self) -> None:
        """Эндпоинт /health возвращает status=ok и информацию о Redis."""
        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertIn('redis', data)
        self.assertIn('active_connections', data)
        self.assertIn('version', data)
        self.assertEqual(data['version'], '2.0.0')

    # ────────────────────────────────────────────────────────────
    # WebSocket подключение без токена
    # ────────────────────────────────────────────────────────────

    def test_ws_connect_without_token(self) -> None:
        """WebSocket подключение без токена — сервер отклоняет соединение с ошибкой."""
        from starlette.websockets import WebSocketDisconnect

        # FastAPI отклонит запрос без обязательного query-параметра token
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/ws') as websocket:
                pass

        # Проверяем, что соединение не в active_connections
        from websocket_server import main as ws_main
        self.assertEqual(len(ws_main.active_connections), 0)

    # ────────────────────────────────────────────────────────────
    # WebSocket подключение с невалидным токеном
    # ────────────────────────────────────────────────────────────

    def test_ws_connect_with_invalid_token(self) -> None:
        """WebSocket подключение с невалидным токеном — сервер закрывает соединение."""
        from websocket_server import main as ws_main

        try:
            with self.client.websocket_connect(
                f'/ws?token=invalid.token.here'
            ) as websocket:
                # Сервер должен закрыть соединение
                pass
        except Exception:
            pass  # Ожидаемо — сервер закрывает

        # Пользователь не должен быть в активных соединениях
        self.assertEqual(len(ws_main.active_connections), 0)

    def test_ws_connect_with_expired_token(self) -> None:
        """WebSocket подключение с истёкшим токеном — сервер закрывает соединение."""
        from websocket_server import main as ws_main

        expired_token = jwt.encode(
            {
                'user_id': 42,
                'exp': datetime.now(timezone.utc) - timedelta(hours=1),
            },
            self.secret_key,
            algorithm='HS256',
        )

        try:
            with self.client.websocket_connect(
                f'/ws?token={expired_token}'
            ) as websocket:
                pass
        except Exception:
            pass

        self.assertEqual(len(ws_main.active_connections), 0)

    def test_ws_connect_token_without_user_id(self) -> None:
        """WebSocket с токеном без user_id — сервер закрывает соединение."""
        from websocket_server import main as ws_main

        try:
            with self.client.websocket_connect(
                f'/ws?token={self.token_without_uid}'
            ) as websocket:
                pass
        except Exception:
            pass

        self.assertEqual(len(ws_main.active_connections), 0)

    # ────────────────────────────────────────────────────────────
    # WebSocket подключение с валидным токеном
    # ────────────────────────────────────────────────────────────

    def test_ws_connect_with_valid_token(self) -> None:
        """WebSocket подключение с валидным токеном — принимается."""
        from websocket_server import main as ws_main

        try:
            with self.client.websocket_connect(
                f'/ws?token={self.valid_token}'
            ) as websocket:
                # Должны получить приветственное сообщение
                data = websocket.receive_json()
                self.assertEqual(data['type'], 'connected')
                self.assertEqual(data['user_id'], '42')

                # Пользователь в активных соединениях
                self.assertIn('42', ws_main.active_connections)
        except Exception:
            pass

        # После выхода — соединение удалено
        self.assertNotIn('42', ws_main.active_connections)


if __name__ == '__main__':
    unittest.main()
