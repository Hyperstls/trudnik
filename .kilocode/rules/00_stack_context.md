@rule global
Используй следующий контекст проекта для всех ответов.

ВАЖНО: версия Python — 3.12 (Dockerfile: FROM python:3.12-slim). История только 3.11 → 3.12.
НЕ предлагай 3.13/3.14 и не указывай их — их нет в проекте.

stack:
  language: "Python 3.12"
  backend:
    web: "Flask 3.1.3 (WSGI, Application Factory + Blueprints)"
    websocket: "FastAPI 0.137.1 (ASGI)"
    asgi_entry: "asgi.py — RouterMiddleware: lifespan+websocket → FastAPI, http → Flask (через a2wsgi.WSGIMiddleware workers=50)"
    deployment: "ПРОД: ОДИН uvicorn-процесс `uvicorn asgi:application --workers 2` (port 8000) обслуживает И HTTP, И WebSocket (/ws). НЕ 'отдельный процесс WS'."
  db:
    # Версии различаются локально и в проде — указывай явно где речь.
    primary_prod: "PostgreSQL 17.6 + PostGIS (Amvera)"
    primary_local: "PostgreSQL 15 + PostGIS 3.4 (docker-compose: postgis/postgis:15-3.4-alpine)"
    api_prod: "PostgREST v14.10 (Amvera)"
    api_local: "PostgREST v12.2.3 (docker-compose: postgrest/postgrest:v12.2.3)"
    access: "requests.Session (app/utils/postgrest_client.py) — см. 07_postgrest_client_api.md"
    response_class: "PostgrestResponse (НЕ Pydantic, НЕ requests.Response)"
  async_tasks:
    broker: "Celery 5.6.3"
    cache_pubsub: "Redis 8.0.0 (прод) / Redis 7-alpine (docker-compose)"
    redis_db: "broker+pubsub — db 0; celery result-backend — db 1 (celery_app.py формирует /1)"
    beat_schedule:  # celery_app.py — 6 задач
      - "drain_notification_outbox (10с)"
      - "ensure_postgrest_role_grants (120с, self-heal грантов ролей)"
      - "expire_old_jobs (3600с)"
      - "cleanup_orphaned_notifications (3600с)"
      - "cleanup_old_email_logs (86400с)"
      - "cleanup_expired_push_subscriptions (3600с)"
  frontend:
    templates: "Jinja2 3.1.6"
    styling: "Tailwind CSS (precompiled tailwind.min.css)"
    js: "Vanilla JS (no React/TypeScript)"
    pwa: "Service Worker + Web Push (VAPID)"
  auth:
    passwords: "bcrypt 12 rounds, формат $2b$ совместим с pgcrypto crypt() — app/utils/auth.py (hash_password/check_password). Fallback-проверка через _login_direct_sql (auth_service)."
    jwt_postgrest: "PGRST_JWT_SECRET; role='authenticated' (app_role=worker/employer/admin) ИЛИ role='service_role' (обход RLS, postgrest_admin_request)"
    jwt_websocket: "WEBSOCKET_JWT_SECRET (user_id + jti only, без role/app_role)"
    csrf: "Session-based (_csrf_token) + X-CSRF-Token header"
  deploy:
    platform: "Amvera (Docker) — см. 06_amvera_deploy.md"
    process_manager: "supervisord: uvicorn(asgi:application, --workers 2), celery_worker(--concurrency=4), celery_beat"
    docker_local: "docker-compose: redis, db, postgrest, pgadmin(profile:debug), celery_worker, celery_beat, web(`python app.py`)"
    ports_local: "DB 5433→5432 | PostgREST 3000 | Redis 6379 | Web 8000 (HTTP; WS локально — отдельный `uvicorn asgi:application --port 8001`) | pgadmin 5050"
  testing:
    framework: "pytest + Playwright — см. 08_testing_and_verify.md"
  monitoring:
    metrics: "prometheus_client; состояние Circuit Breaker через get_circuit_breaker_state()"
  monetization: "DISABLED (MONETIZATION_ENABLED=false, все функции бесплатны)"
