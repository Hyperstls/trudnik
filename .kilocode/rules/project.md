Проект «Трудник»

Стек
Python 3.14 + Flask (WSGI) + FastAPI (ASGI/WebSocket)PostgreSQL 15 + PostGIS + PostgREST v12Redis 7 (Celery broker + Pub/Sub + кэш)Celery (worker + beat)Jinja2 + TailwindCSS + Vanilla JSDocker (локально) + Amvera (продакшен)

Масштаб
21+ таблиц, 74+ SQL-миграции, 12 RPC-функций

Архитектура
Монолит: 13+ Flask Blueprint'ов в app/blueprints/5 сервисов в app/services/WebSocket через asgi.py (FastAPI + Redis Pub/Sub)RPC-функции через PostgREST (SECURITY DEFINER)RLS на всех таблицах

Локальная разработка (Docker) DB: localhost:5433→5432PostgREST: localhost:3000Redis: localhost:6379Web: localhost:8000WebSocket: localhost:8001

Правила 
Все данные через PostgREST (не прямой SQL)Мутации через RPC (accept_application, reject_application, и т.д.)Фронтенд — Jinja2 шаблоны (не React/Vue/SPA)Тесты — PyTest + Playwright, mock в app/testing/mock_postgrest.pyБезопасность: CSP nonce, CSRF, Rate Limiting, Circuit Breaker.env содержит продакшен-переменные Amvera; локально — Docker