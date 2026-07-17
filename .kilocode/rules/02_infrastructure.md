@rule debug
При анализе трейсстэков и логов ВСЕГДА учитывай среду выполнения.

1. Процессы и точка входа (asgi.py):
   - ПРОД (Amvera, supervisord): ОДИН uvicorn-процесс `uvicorn asgi:application --workers 2` на порту 8000 обслуживает И HTTP, И WebSocket.
   - asgi.py = RouterMiddleware: scope `websocket`+`lifespan` → FastAPI (websocket_server/main.py); scope `http` → Flask (через a2wsgi.WSGIMiddleware, workers=50).
   - a2wsgi ИСПОЛЬЗУЕТСЯ. Утверждение «WS — отдельный процесс, не через a2wsgi» НЕВЕРНО и ведёт к ложному диагностическому пути.
   - WS endpoint: /ws на ТОМ ЖЕ порту 8000. WEBSOCKET_PORT=8001 в .env нужен только для ЛОКАЛЬНОГО ручного запуска `uvicorn asgi:application --port 8001` (docker-compose `web` запускает `python app.py` = Flask WSGI dev-сервер БЕЗ WS).
   - 3 программы supervisord: uvicorn (stopwaitsecs=35), celery_worker (stopwaitsecs=310), celery_beat (stopwaitsecs=30).

2. WebSocket (FastAPI):
   - websocket_server/main.py + auth.py; JSON-RPC поверх /ws.
   - active_connections: dict[str, set[WebSocket]] (multi-connection, до 3 на пользователя).
   - Анализируй обрывы на уровне FastAPI WebSocket, не на уровне WSGI/Flask.
   - JWT для WS отдельный (WEBSOCKET_JWT_SECRET): только user_id + jti.

3. Celery + Redis (celery_app.py):
   - Брокер: Redis db 0. Backend: Redis db 1 (формируется как /1 от REDIS_URL).
   - Конфиг: task_time_limit=300, task_soft_time_limit=240, worker_prefetch_multiplier=1, task_acks_late=True, task_reject_on_worker_lost=True, worker_shutdown_timeout=60, broker_connection_retry_on_startup=True, task_default_retry_delay=60, task_max_retries=3.
   - Базовый класс FlaskContextTask инъектит g.request_id в kwargs задачи (_request_id) для сквозной трассировки.
   - Beat: 6 задач (см. 00_stack_context.md). drain_notification_outbox — каждые 10с.
   - Ищи: таймауты (soft 240 / hard 300), потерю сообщений (acks_late + prefetch=1), задачи длиннее 300с (будут убиты — подними soft/hard лимит или дроби задачу).

4. JWT:
   - 2 секрета: PGRST_JWT_SECRET (PostgREST) и WEBSOCKET_JWT_SECRET (WS).
   - PostgREST JWT: role='authenticated' (app_role=worker/employer/admin) или role='service_role' (обход RLS).
   - WS JWT: только user_id + jti.
   - Проверяй jti в Redis blacklist (ключ jti_blacklist:{jti}).

5. Миграции НЕ применяются автоматически:
   - entrypoint.sh НЕ запускает миграции. Применяются вручную:
     `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py`
   - Учёт применённых — таблица schema_migrations.

6. Healthcheck (разные endpoints — не путай):
   - Dockerfile HEALTHCHECK → /ready.
   - docker-compose web healthcheck → /health.
   - Amvera (снаружи): https://<slug>.amvera.io/health (см. 06_amvera_deploy.md).
