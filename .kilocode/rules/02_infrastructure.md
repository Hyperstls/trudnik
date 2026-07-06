@rule debugПри анализе учитывай гибридную архитектуру:

HTTP (Flask WSGI) и WebSocket (FastAPI ASGI) живут в одном процессе через asgi.py (a2wsgi).
Celery воркеры общаются с Redis (брокер db 0, backend db 1).
WebSocket использует dict[str, set[WebSocket]] для мульти-вкладок.
Если падает Celery — проверяй таймауты (time-limit=300) и памяти в supervisord.
Если отваливается WS — проверяй jti_blacklist в Redis и WEBSOCKET_JWT_SECRET.