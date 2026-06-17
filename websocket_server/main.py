"""
Основное FastAPI-приложение WebSocket-сервера Trudnik.

Обеспечивает:
- WebSocket-эндпоинт с JWT-аутентификацией
- Redis Pub/Sub слушатель для мгновенной доставки уведомлений и сообщений чата
- Healthcheck эндпоинт

Запуск:
    uvicorn websocket_server.main:app --host 0.0.0.0 --port ${WEBSOCKET_PORT:-8001}
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from .auth import verify_token

# ═══════════════════════════════════════════════════════════════
# Логирование
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("websocket_server")

# ═══════════════════════════════════════════════════════════════
# Конфигурация из переменных окружения
# ═══════════════════════════════════════════════════════════════

REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CORS_ORIGINS: list[str] = os.environ.get("WEBSOCKET_CORS_ORIGINS", "*").split(",")
WEBSOCKET_PORT: int = int(os.environ.get("WEBSOCKET_PORT", "8001"))

# Каналы Redis Pub/Sub, которые слушает сервер
NOTIFICATIONS_CHANNEL: str = "notifications"
CHAT_CHANNEL: str = "chat"

# ═══════════════════════════════════════════════════════════════
# Глобальное состояние
# ═══════════════════════════════════════════════════════════════

# Словарь активных WebSocket-соединений: {user_id: WebSocket}
active_connections: dict[str, WebSocket] = {}

# Клиент Redis (устанавливается в lifespan)
redis_client: aioredis.Redis | None = None

# Флаг для graceful shutdown слушателя Pub/Sub
shutdown_event: asyncio.Event = asyncio.Event()


# ═══════════════════════════════════════════════════════════════
# Redis Pub/Sub слушатель (фоновая задача)
# ═══════════════════════════════════════════════════════════════

async def redis_pubsub_listener() -> None:
    """
    Фоновая задача, подписанная на каналы Redis Pub/Sub.
    При получении сообщения находит WebSocket пользователя и отправляет ему данные.

    Каналы:
        - notifications: {'type': 'notification', 'user_id': ..., 'data': {...}}
        - chat:          {'type': 'chat', 'user_id': ..., 'data': {...}}
    """
    global redis_client

    if redis_client is None:
        logger.error("Redis-клиент не инициализирован, слушатель Pub/Sub не запущен")
        return

    logger.info("Запуск Redis Pub/Sub слушателя (каналы: %s, %s)", NOTIFICATIONS_CHANNEL, CHAT_CHANNEL)

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(NOTIFICATIONS_CHANNEL, CHAT_CHANNEL)

    try:
        while not shutdown_event.is_set():
            # Используем таймаут для возможности graceful shutdown
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message is None:
                continue

            try:
                data_str: str = message.get("data", "{}")

                # data может быть bytes или str в зависимости от версии redis-py
                if isinstance(data_str, bytes):
                    data_str = data_str.decode("utf-8")

                payload: dict[str, Any] = json.loads(data_str)
                user_id: str | None = payload.get("user_id")
                channel: str = message.get("channel", "").decode("utf-8") if isinstance(message.get("channel"), bytes) else str(message.get("channel", ""))

                if user_id is None:
                    logger.warning("Сообщение из канала '%s' без user_id, пропускаем", channel)
                    continue

                websocket = active_connections.get(str(user_id))
                if websocket is not None:
                    try:
                        await websocket.send_json(payload)
                        logger.debug("Отправлено сообщение пользователю %s через канал '%s'", user_id, channel)
                    except Exception as exc:
                        logger.error("Ошибка отправки WebSocket-сообщения пользователю %s: %s", user_id, exc)
                        # Удаляем «мёртвое» соединение
                        active_connections.pop(str(user_id), None)
                else:
                    logger.debug("Пользователь %s не в сети, сообщение из канала '%s' пропущено", user_id, channel)

            except json.JSONDecodeError as exc:
                logger.error("Ошибка разбора JSON из Redis Pub/Sub: %s", exc)
            except Exception as exc:
                logger.error("Неожиданная ошибка при обработке Pub/Sub-сообщения: %s", exc)

    except asyncio.CancelledError:
        logger.info("Задача слушателя Pub/Sub отменена")
    finally:
        await pubsub.unsubscribe(NOTIFICATIONS_CHANNEL, CHAT_CHANNEL)
        await pubsub.close()
        logger.info("Redis Pub/Sub слушатель остановлен")


# ═══════════════════════════════════════════════════════════════
# Lifespan (startup / shutdown)
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения: подключение/отключение Redis."""
    global redis_client, shutdown_event

    shutdown_event.clear()

    # ── Startup ───────────────────────────────────────────────
    logger.info("Подключение к Redis: %s", REDIS_URL)
    try:
        redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis подключён успешно")
    except Exception as exc:
        logger.error("Не удалось подключиться к Redis: %s", exc)
        redis_client = None

    # Запускаем фоновую задачу Pub/Sub слушателя
    listener_task: asyncio.Task[None] | None = None
    if redis_client is not None:
        listener_task = asyncio.create_task(redis_pubsub_listener())

    yield  # Приложение работает

    # ── Shutdown ──────────────────────────────────────────────
    logger.info("Завершение работы WebSocket-сервера...")
    shutdown_event.set()

    # Закрываем все активные WebSocket-соединения
    for uid, ws in list(active_connections.items()):
        try:
            await ws.close(code=status.WS_1001_GOING_AWAY)
        except Exception:
            pass
        logger.info("WebSocket-соединение пользователя %s закрыто при завершении сервера", uid)
    active_connections.clear()

    # Останавливаем слушатель Pub/Sub
    if listener_task is not None:
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

    # Закрываем Redis-соединение
    if redis_client is not None:
        await redis_client.close()
        logger.info("Redis-соединение закрыто")


# ═══════════════════════════════════════════════════════════════
# FastAPI-приложение
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Trudnik WebSocket Server",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: разрешить все origins для разработки (настраивается через WEBSOCKET_CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# WebSocket эндпоинт
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT-токен аутентификации"),
) -> None:
    """
    WebSocket-эндпоинт для мгновенной доставки уведомлений и сообщений чата.

    Аутентификация: JWT-токен через query-параметр ?token=...
    После успешной верификации соединение регистрируется в active_connections.
    """
    # Верификация токена
    payload: dict | None = verify_token(token)
    if payload is None:
        logger.warning("Попытка WebSocket-подключения с невалидным токеном")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Невалидный JWT-токен")
        return

    user_id: str = str(payload.get("user_id", ""))
    if not user_id:
        logger.warning("WebSocket-подключение без user_id в токене")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Токен не содержит user_id")
        return

    # Принимаем соединение
    await websocket.accept()
    active_connections[user_id] = websocket
    logger.info("Пользователь %s подключился по WebSocket (всего онлайн: %d)", user_id, len(active_connections))

    try:
        # Отправляем приветственное сообщение
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "Подключение установлено",
        })

        # Держим соединение открытым, принимая входящие сообщения (ping/pong и т.д.)
        while True:
            data = await websocket.receive_text()
            # Игнорируем входящие сообщения (клиент не должен слать данные, кроме ping)
            logger.debug("Получено сообщение от пользователя %s: %s", user_id, data[:100])

    except WebSocketDisconnect:
        logger.info("Пользователь %s отключился от WebSocket", user_id)
    except Exception as exc:
        logger.error("Ошибка WebSocket-соединения пользователя %s: %s", user_id, exc)
    finally:
        # Удаляем соединение из активных
        active_connections.pop(user_id, None)
        logger.info("Пользователь %s удалён из активных соединений (всего онлайн: %d)", user_id, len(active_connections))


# ═══════════════════════════════════════════════════════════════
# Healthcheck
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def healthcheck() -> dict[str, Any]:
    """
    Эндпоинт проверки работоспособности сервера.
    Проверяет подключение к Redis и возвращает количество активных соединений.
    """
    redis_status: str = "unknown"
    if redis_client is not None:
        try:
            await redis_client.ping()
            redis_status = "ok"
        except Exception as exc:
            redis_status = f"error: {exc}"
    else:
        redis_status = "not_connected"

    return {
        "status": "ok",
        "redis": redis_status,
        "active_connections": len(active_connections),
        "version": "2.0.0",
    }
