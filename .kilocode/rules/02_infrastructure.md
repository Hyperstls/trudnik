@rule debug
При анализе трейсстэков и логов ВСЕГДА учитывай среду выполнения:

1. Docker + supervisord: 
   - 3 процесса: uvicorn (Flask+FastAPI asgi), celery_worker (--concurrency=4), celery_beat
   - stopwaitsecs=310 для celery (больше time-limit=300)
   - Проверяй конфиги перезапуска и лимиты памяти.

2. Celery + Redis:
   - Брокер: Redis (db 0), Backend: Redis (db 1)
   - Задача drain_notification_outbox выполняется каждые 10 секунд
   - Ищи проблемы с таймаутами (time-limit=300) и потерей сообщений.

3. WebSocket (FastAPI):
   - Отдельный ASGI-процесс (websocket_server/main.py), НЕ через a2wsgi
   - asgi.py маршрутизирует: lifespan+websocket → FastAPI, HTTP → Flask (через WSGIMiddleware)
   - active_connections: dict[str, set[WebSocket]] (multi-connection, до 3 на пользователя)
   - Анализируй обрывы на уровне FastAPI WebSocket, не WSGI.

4. JWT:
   - 2 разных секрета: PGRST_JWT_SECRET (для PostgREST) и WEBSOCKET_JWT_SECRET (для WS)
   - JWT для PostgREST: role='authenticated', app_role='worker'/'employer'/'admin'
   - JWT для WebSocket: только user_id + jti, без role/app_role
   - Проверяй jti в Redis blacklist (ключ jti_blacklist:{jti})
```
