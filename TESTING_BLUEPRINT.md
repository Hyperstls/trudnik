# Трудник (Trudnik) — Индексный навигационный хаб документации

> **Актуализировано:** 2026-06-17
> **Ветка:** `main` (монетизация отключена, все задания публикуются как `is_paid=True`)
> **Статус:** этот файл теперь служит индексным хабом. Полное содержимое разнесено по дочерним документам в [`docs/`](docs/).

---

## О проекте

**«Трудник»** — веб-приложение (PWA) для платформы найма трудников в религиозных организациях (храмы, церкви, мечети). Позволяет работодателям публиковать задания, а трудникам — находить временную подработку, откликаться и получать оплату.

Две роли: **работодатель** (employer) и **трудник** (worker). Приложение построено как монолитное Flask-приложение с 13 Blueprint-модулями, базой данных Supabase (PostgreSQL + PostgREST), фоновыми задачами на Celery, real-time уведомлениями через WebSocket (FastAPI) и Redis Pub/Sub, а также Web Push и Email-рассылками.

**Ключевые возможности:** поиск и фильтрация заданий/трудников, управление откликами, чат, система приглашений, оценки, избранное, чёрный список, админ-панель, PWA с офлайн-режимом.

---

## Оглавление документации

| Документ | Содержание |
|----------|-----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Общая архитектура, технологический стек, структура проекта, схема компонентов, потоки данных, инфраструктура и деплой |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | Все маршруты и API-эндпоинты (REST, RPC, WebSocket) |
| [`docs/BUSINESS_LOGIC.md`](docs/BUSINESS_LOGIC.md) | Бизнес-логика, модель данных, состояния заданий/откликов, жизненные циклы |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Безопасность: аутентификация, CSRF, CSP, Rate Limiting, Circuit Breaker, RLS |
| [`docs/TEST_CHECKLIST.md`](docs/TEST_CHECKLIST.md) | Тестовые сценарии и чеклисты (ручное + автоматизированное тестирование) |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | Фронтенд: страницы, JavaScript, UI-компоненты, адаптивность, доступность, PWA |
| [`docs/E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) | End-to-end сценарии по ролям (worker, employer, admin) |
| [`docs/notifications-v2.md`](docs/notifications-v2.md) | Спецификация системы уведомлений v2 (WebSocket + Push + Email) |
| [`docs/PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) | Контекст проекта, цели, roadmap |

---

## Легенда: как ориентироваться в документации

| Вы ... | Вам нужен документ |
|--------|-------------------|
| **Новый разработчик**, хотите понять проект | Начните с [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) → затем [`BUSINESS_LOGIC.md`](docs/BUSINESS_LOGIC.md) |
| **Пишете тесты** или проверяете функционал | [`TEST_CHECKLIST.md`](docs/TEST_CHECKLIST.md) + [`E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) |
| **Работаете с API** или интеграцией | [`API_REFERENCE.md`](docs/API_REFERENCE.md) |
| **Аудитируете безопасность** | [`SECURITY.md`](docs/SECURITY.md) |
| **Работаете с фронтендом** | [`FRONTEND.md`](docs/FRONTEND.md) |
| **Работаете с уведомлениями** | [`notifications-v2.md`](docs/notifications-v2.md) |
| **Хотите понять бизнес-правила** | [`BUSINESS_LOGIC.md`](docs/BUSINESS_LOGIC.md) |
| **Планируете архитектурные изменения** | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) + [`PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) |

---

## Быстрые ссылки на ключевые файлы исходного кода

### Ядро приложения

| Файл | Описание |
|------|----------|
| [`app.py`](app.py) | Точка входа WSGI |
| [`asgi.py`](asgi.py) | Unified ASGI: WebSocket (FastAPI) + HTTP (Flask) |
| [`app/__init__.py`](app/__init__.py) | Фабрика `create_app()`, security headers, CSRF, контекст-процессоры |
| [`app/config.py`](app/config.py) | Конфигурация (ENV-переменные, бизнес-константы) |
| [`app/decorators.py`](app/decorators.py) | `@login_required`, `@role_required` |
| [`app/utils.py`](app/utils.py) | `supabase_request`, `CircuitBreaker`, `rate_limit`, хелперы |

### Блюпринты (13 модулей)

| Файл | Маршруты |
|------|----------|
| [`app/blueprints/auth.py`](app/blueprints/auth.py) | `/login`, `/register`, `/logout` |
| [`app/blueprints/jobs.py`](app/blueprints/jobs.py) | `/`, `/workers`, `/job/new`, `/my-jobs`, `/jobs/<id>` |
| [`app/blueprints/jobs_api.py`](app/blueprints/jobs_api.py) | `/api/search/jobs`, `/api/search/workers`, `/api/invite` |
| [`app/blueprints/applications.py`](app/blueprints/applications.py) | `/apply`, `/my-applications`, accept/reject/withdraw |
| [`app/blueprints/admin.py`](app/blueprints/admin.py) | `/admin` |
| [`app/blueprints/profile.py`](app/blueprints/profile.py) | `/profile`, `/verify-employer`, delete account |
| [`app/blueprints/chat.py`](app/blueprints/chat.py) | `/chats`, `/chat/<id>`, `/api/send_message` |
| [`app/blueprints/employers.py`](app/blueprints/employers.py) | `/employers`, `/employers/<id>` |
| [`app/blueprints/favorites.py`](app/blueprints/favorites.py) | `/favorites` |
| [`app/blueprints/notifications.py`](app/blueprints/notifications.py) | `/notifications`, настройки |
| [`app/blueprints/ratings.py`](app/blueprints/ratings.py) | `/api/ratings`, `/ratings/user/<id>` |
| [`app/blueprints/blacklist.py`](app/blueprints/blacklist.py) | `/blacklist` |
| [`app/blueprints/seo.py`](app/blueprints/seo.py) | `/robots.txt`, `/sitemap.xml` |

### Сервисы (5)

| Файл | Назначение |
|------|-----------|
| [`app/services/job_service.py`](app/services/job_service.py) | Поиск и фильтрация заданий/трудников |
| [`app/services/notification_service.py`](app/services/notification_service.py) | Создание и управление уведомлениями |
| [`app/services/email_service.py`](app/services/email_service.py) | Отправка email через Celery |
| [`app/services/push_service.py`](app/services/push_service.py) | Web Push уведомления (VAPID) |
| [`app/services/redis_publisher.py`](app/services/redis_publisher.py) | Публикация событий в Redis Pub/Sub |

### Фоновые задачи (Celery)

| Файл | Назначение |
|------|-----------|
| [`app/tasks/celery_app.py`](app/tasks/celery_app.py) | Инициализация Celery (Redis брокер) |
| [`app/tasks/email_tasks.py`](app/tasks/email_tasks.py) | Email-задачи |
| [`app/tasks/push_tasks.py`](app/tasks/push_tasks.py) | Push-задачи |

### Инфраструктура

| Файл | Описание |
|------|----------|
| [`Dockerfile`](Dockerfile) | Docker-образ |
| [`docker-compose.yml`](docker-compose.yml) | Локальная инфраструктура (redis, websocket, celery) |
| [`render.yaml`](render.yaml) | Деплой на Render.com |
| [`requirements.txt`](requirements.txt) | Зависимости |
| [`migrations/`](migrations/) | SQL-миграции (001–047) |

---

> **Примечание:** Этот файл ранее содержал ~1700 строк полной документации (архитектура, API, бизнес-логика, безопасность, тестовые сценарии). Теперь всё содержимое разнесено по тематическим дочерним документам в [`docs/`](docs/). Данный файл служит только индексным навигационным хабом.
