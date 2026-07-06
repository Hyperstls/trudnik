@rule global
Используй следующий контекст проекта для всех ответов:

stack:
  language: "Python 3.12"
  backend:
    web: "Flask 3.1.3 (WSGI, Application Factory + Blueprints)"
    websocket: "FastAPI 0.137.1 (ASGI, отдельный процесс)"
    asgi_entry: "asgi.py (RouterMiddleware: HTTP→Flask, WS→FastAPI)"
  db:
    primary: "PostgreSQL 15 + PostGIS"
    api: "PostgREST v12.2.3 (HTTP REST, НЕ ORM)"
    access: "requests.Session (app/utils/postgrest_client.py)"
    response_class: "PostgrestResponse (НЕ Pydantic)"
  async_tasks:
    broker: "Celery 5.6.3"
    cache: "Redis 8.0.0"
    beat_schedule: ["drain_notification_outbox (10s)", "expire_old_jobs (1h)"]
  frontend:
    templates: "Jinja2 3.1.6"
    styling: "Tailwind CSS (precompiled tailwind.min.css)"
    js: "Vanilla JS (no React/TypeScript)"
    pwa: "Service Worker + Web Push (VAPID)"
  auth:
    passwords: "pgcrypto crypt() (Blowfish, 12 rounds)"
    jwt_postgrest: "PGRST_JWT_SECRET (role=authenticated, app_role=worker/employer/admin)"
    jwt_websocket: "WEBSOCKET_JWT_SECRET (user_id + jti only)"
    csrf: "Session-based (_csrf_token) + X-CSRF-Token header"
  deploy:
    platform: "Amvera (Docker)"
    process_manager: "supervisord (uvicorn + celery_worker + celery_beat)"
    workers: "uvicorn --workers 1, celery --concurrency 4"
  testing:
    framework: "pytest"
    e2e: "Playwright"
  monetization: "DISABLED (MONETIZATION_ENABLED=false, все функции бесплатны)"
```