@rule global
Проект «Трудник» — платформа разовой подработки (worker ↔ employer).

КАНОНИЧЕСКИЕ ВЕРСИИ И СТЕК — в 00_stack_context.md (НЕ дублируй версии здесь).
Здесь только сводка назначения, архитектуры и ключевых портов.

Назначение
- Соискатели (worker) откликаются на вакансии; работодатели (employer) принимают/отклоняют.
- Роли: worker / employer / admin. Регистрация, профили, отклики, чат, рейтинг, уведомления (web/email/push), избранное, чёрный список, приглашения.

Архитектура (монолит)
- Flask (WSGI) + FastAPI (WebSocket) в ОДНОМ uvicorn-процессе через asgi.py (RouterMiddleware + a2wsgi). См. 02_infrastructure.md.
- Blueprints (app/blueprints/, 20): auth, core, profile, jobs, jobs_api, applications, chat, notifications, favorites, blacklist, ratings, employers, seo, messenger_verify + admin_{dashboard,users,jobs,verification,dictionaries,diagnostics}.
- Сервисы (app/services/, 13): auth, application, job, notification, notification_dispatcher, push, email, ratings, invitation, admin, payment, storage, redis_publisher.
- Celery (app/tasks/): celery_app, notification_tasks, email_tasks, push_tasks, maintenance_tasks. Beat — 6 задач (см. 00).
- WebSocket (websocket_server/): main.py, auth.py; JSON-RPC поверх /ws.
- Доступ к данным: ТОЛЬКО через PostgREST (HTTP). См. 01_db_access.md и 07_postgrest_client_api.md.
- Мутации — через RPC (PL/pgSQL, SECURITY DEFINER). RLS на всех таблицах; app_role из JWT claim.

Масштаб (сверено с БД и migrations/ на 2026-08-01)
- ~31 таблица (25 бизнес + user_reports + site_pages + системные);
  47+ файлов SQL-миграций (последняя #137, с консолидациями); ~30 SECURITY DEFINER RPC-функций.
  Phase 3: жалобы + авто-заморозка (Part B), мессенджер-верификация MAX/Telegram (Part A), anti-DDoS (глобальный rate-limit + MAX_CONTENT_LENGTH).

Локальная разработка (docker-compose)
- DB 5433→5432 (PostgreSQL 15 + PostGIS 3.4) | PostgREST 3000 (v14, dev=prod parity) | Redis 6379 (db0 broker, db1 backend) | Web 8000 (HTTP) | pgadmin 5050 (профиль debug).
- WebSocket локально: `uvicorn asgi:application --port 8001` (docker-compose `web` = Flask dev-server, WS не обслуживает).

Деплой / тесты
- Продакшен: Amvera (Docker) — 06_amvera_deploy.md.
- Тесты: pytest + Playwright — 08_testing_and_verify.md.
- Монетизация: отключена (MONETIZATION_ENABLED=false).
