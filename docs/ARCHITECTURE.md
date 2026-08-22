# Архитектура приложения «Трудник»

> **Актуализировано:** 2026-07-17
> **Ветка:** `main` (монетизация отключена, `MONETIZATION_ENABLED=false`)
> **Версия документа:** 5.1 — актуализация стека по коду на 2026-07: Python 3.12, Flask 3.1.3, FastAPI 0.137.1 + a2wsgi, PostgreSQL 17.6/15 + PostGIS, PostgREST v14.10/v12.2.3, 126+ миграций, ~19 blueprints, 13 сервисов

---

## Оглавление

1. [Обзор системы](#1-обзор-системы)
2. [Технологический стек](#2-технологический-стек)
3. [Структура проекта](#3-структура-проекта)
4. [Схема взаимодействия компонентов](#4-схема-взаимодействия-компонентов)
5. [Потоки данных](#5-потоки-данных)
6. [Инфраструктура и деплой](#6-инфраструктура-и-деплой)

---

## 1. Обзор системы

**«Трудник»** — веб-приложение (PWA) для быстрого поиска временной подработки в религиозных организациях (храмы, церкви, мечети). Две роли пользователей:

- **Работодатель (employer)** — публикует задания, управляет откликами, приглашает трудников
- **Трудник (worker)** — ищет задания, откликается, получает оплату

Архитектурный стиль: **монолитное Flask-приложение**, разбитое на ~19 модульных Blueprint'ов, с внешней базой данных PostgreSQL 17.6 + PostGIS (Amvera) через PostgREST API, фоновыми задачами на Celery и real-time уведомлениями через WebSocket.

**Ключевые особенности:**
- Бесплатный режим (монетизация отключена в main)
- PWA с Service Worker и офлайн-режимом
- WebSocket для чата и live-уведомлений
- Push-уведомления (Web Push API + Email)
- Полная безопасность: CSP, CSRF, Rate Limiting, Circuit Breaker, RLS

---

## 2. Технологический стек

| Слой | Технологии |
|------|-----------|
| **Backend** | Python 3.12 + Flask 3.1.3 (WSGI) |
| **ASGI/WebSocket** | FastAPI 0.137.1 + uvicorn + a2wsgi 1.10.0 (`asgi.py`, единый процесс HTTP+WS) |
| **Фоновые задачи** | Celery 5.6.3 (worker + beat) |
| **Брокер сообщений** | Redis 8 (прод) / Redis 7-alpine (локально) — Celery broker + Pub/Sub + кеш |
| **База данных** | PostgreSQL 17.6 + PostGIS (прод Amvera) / PostgreSQL 15 + PostGIS 3.4 (локально) + PostgREST (v14.10 прод / v12.2.3 локально) + нативная JWT-аутентификация |
| **RPC** | PostgreSQL функции (`accept_application`, `reject_application`, `apply_job_atomic`, `delete_job_cascade`, `delete_user_cascade`, `get_job_stats`, `nearby_jobs`, `force_complete_job`, `cancel_job_atomic`, `cancel_worker_atomic`, `rate_user_atomic`, `resolve_user_atomic`, `login_user`, `register_user`, `change_password`) |
| **Фронтенд** | Jinja2 3.1.6 + TailwindCSS (precompiled `tailwind.min.css`) + Vanilla JS (без React/TypeScript) + PWA |
| **Карты** | Яндекс.Карты API |
| **Реальное время** | WebSocket (FastAPI) + Redis Pub/Sub |
| **Push-уведомления** | Web Push API (VAPID) + Email (SMTP) |
| **Деплой** | Amvera (Docker), `amvera.yaml` (containerPort 8000) |
| **Тестирование** | pytest + Playwright + in-memory mock PostgREST (`app/testing/mock_postgrest.py`) |
| **Безопасность** | CSP nonce + CSRF + Rate Limiting + Circuit Breaker + RLS + email-валидация (RFC 5322) + защита от SQL-инъекций + дифференцированные таймауты |

---

## 3. Структура проекта

```
trudnik/
├── app.py                          # Точка входа WSGI: from app import app
├── asgi.py                         # Unified ASGI: WebSocket → FastAPI, HTTP → Flask
├── Dockerfile                      # Docker-образ (Python 3.12-slim + uvicorn)
├── docker-compose.yml              # Сервисы: redis, db, postgrest, pgadmin(debug), celery_worker, celery_beat, web
├── amvera.yaml                     # Деплой на Amvera (Docker, containerPort 8000)
├── requirements.txt                # Flask, FastAPI, Celery, Redis, pywebpush, etc.
├── requirements-dev.txt            # Зависимости для разработки
├── tailwind.config.js              # TailwindCSS конфигурация
├── twa-config.json                 # Trusted Web Activity для Google Play
├── pytest.ini                      # PyTest конфигурация
├── .env.example                    # Шаблон переменных окружения
├── README.md                       # Описание проекта
│
├── app/
│   ├── __init__.py                 # create_app() — фабрика приложения, security headers, CSRF, контекст-процессоры
│   ├── config.py                   # Config — переменные окружения (SECRET_KEY, POSTGREST_*, REDIS_URL, SMTP_*, VAPID_*, WEBSOCKET_*)
│   ├── decorators.py               # @login_required, @role_required
│   ├── utils/                     # ПАКЕТ app/utils/: postgrest_client.py, auth.py, geo.py, validators.py, redis_cache.py, rate_limit_decorator.py и др.
│   │
│   ├── blueprints/                 # ~19 блюпринтов (включая 6 admin_*)
│   │   ├── __init__.py
│   │   ├── auth.py                 # /login, /register, /logout
│   │   ├── jobs.py                 # /, /workers, /job/new, /my-jobs, /jobs/<id>, etc.
│   │   ├── jobs_api.py             # /api/invite, /api/invitations, /api/skills (поиск — в HTML-каталоге `/`)
│   │   ├── applications.py         # /apply, /my-applications, accept/reject/withdraw
│   │   ├── admin_dashboard.py      # /admin — расщеплён на admin_dashboard / admin_users / admin_jobs / admin_verification / admin_dictionaries / admin_diagnostics (отдельного admin.py НЕТ)
│   │   ├── profile.py              # /profile, /profile/update, /verify-employer, delete account
│   │   ├── chat.py                 # /chats, /chat/<id>, /api/send_message, poll
│   │   ├── employers.py            # /employers, /employers/<id>, избранное API
│   │   ├── favorites.py            # /favorites, /favorite/<id>, API избранного
│   │   ├── notifications.py        # /notifications, настройки уведомлений
│   │   ├── ratings.py              # /api/ratings, /ratings/user/<id>, /jobs/<id>/rate-workers
│   │   ├── blacklist.py            # /blacklist, /blacklist/<id>, /unblock/<id>
│   │   └── seo.py                  # /robots.txt, /sitemap.xml
│   │
│   ├── services/                   # 13 сервисов: auth, application, job, notification, notification_dispatcher, email, push, ratings, invitation, admin, payment, storage, redis_publisher
│   │   ├── __init__.py
│   │   ├── job_service.py          # search_jobs, search_workers, check_job_visibility
│   │   ├── notification_service.py # create, get_notifications, mark_read, preferences
│   │   ├── email_service.py        # Отправка email (SMTP) через Celery
│   │   ├── push_service.py         # Web Push уведомления (VAPID)
│   │   └── redis_publisher.py      # Публикация событий в Redis Pub/Sub
│   │
│   ├── tasks/                      # Celery-задачи
│   │   ├── __init__.py
│   │   ├── celery_app.py           # Инициализация Celery (Redis брокер, 6 beat-задач: drain_notification_outbox 10с, ensure_postgrest_role_grants 120с, expire_old_jobs, cleanup_*; time_limit=300/soft=240)
│   │   ├── email_tasks.py          # Фоновые задачи отправки email
│   │   └── push_tasks.py           # Фоновые задачи push-уведомлений
│   │
│   └── templates/                  # <!-- УСТАРЕЛО: Email-шаблоны в app/templates/ → templates/email/ -->
│
├── templates/                      # Jinja2-шаблоны (30 файлов)
│   ├── base.html                   # Базовый layout (навигация, заголовки, скрипты, PWA)
│   ├── index.html                  # Главная страница (поиск заданий/трудников)
│   ├── workers.html                # Список трудников с фильтрацией
│   ├── employers.html              # Список работодателей
│   ├── employer_detail.html        # Профиль работодателя
│   ├── job_detail.html             # Детальная страница задания
│   ├── job_new.html                # Форма создания задания
│   ├── my_jobs.html                # Мои задания (работодатель)
│   ├── my_applications.html        # Мои отклики (трудник)
│   ├── login.html                  # Вход
│   ├── register.html               # Регистрация
│   ├── profile.html                # Профиль (работодатель)
│   ├── profile_worker.html         # Профиль (трудник)
│   ├── verify_employer.html        # Верификация работодателя
│   ├── chat.html                   # Чат
│   ├── chats_list.html             # Список чатов
│   ├── favorites.html              # Избранное
│   ├── notifications.html          # Уведомления
│   ├── notification_settings.html  # Настройки уведомлений
│   ├── invitations.html            # Приглашения
│   ├── blacklist.html              # Чёрный список
│   ├── admin.html                  # Админ-панель
│   ├── rate_workers.html           # Оценка трудников
│   ├── user_ratings.html           # Рейтинги пользователя
│   ├── error.html                  # Страница ошибки
│   ├── offline.html                # Офлайн-страница (PWA)
│   ├── sitemap.xml                 # Sitemap
│   ├── _filter_skills.html         # Include: фильтр навыков
│   ├── _icons.html                 # Include: иконки
│   └── _sort_panel.html            # Include: панель сортировки
│
├── static/                         # CSS, JS, изображения, PWA (sw.js, manifest.json)
│
├── websocket_server/               # WebSocket-сервер (FastAPI + Redis Pub/Sub)
│
├── migrations/                     # SQL-миграции (126+ файлов, 001–1NN)
│   ├── 001_setup_rls.sql
│   ├── ... (002–047 — см. историю коммитов)
│   ├── 047_fix_security_linter_critical.sql
│   ├── 048_atomic_apply_job.sql
│   ├── 049_fix_cloud_schema_alignment.sql    # Восстановление облачных колонок jobs
│   ├── 050_fix_profiles_cloud_alignment.sql  # Добавление колонок profiles + fix preferred_religion
│   ├── 051_fix_service_role_grants.sql       # GRANT service_role на справочные таблицы
│   ├── 052_add_job_stats_rpc.sql             # RPC get_job_stats
│   ├── 053_fix_critical_type_mismatches.sql  # varchar→text, numeric→float8
│   ├── 054_create_missing_cloud_tables.sql   # monetization_settings, receipts, _archive_contact_payments
│   ├── 055_fix_table_structures.sql          # employer_details, favorites, job_photos, invitations, ratings
│   ├── 056_add_nearby_jobs_rpc.sql           # RPC nearby_jobs (PostGIS)
│   ├── ALL_PENDING.sql
│   └── run_all_safe.sql            # <!-- УСТАРЕЛО: supabase_check.sql / supabase_schema.json удалены -->
│
├── docs/                           # Документация (актуальные документы)
│   ├── ARCHITECTURE.md             # Этот документ
│   ├── API_REFERENCE.md            # Все маршруты и API-эндпоинты
│   ├── BUSINESS_LOGIC.md           # Бизнес-логика, модель данных, состояния
│   ├── BUTTON_REGISTRY.md          # Реестр всех кнопок и UI-элементов
│   ├── SECURITY.md                 # Безопасность (аутентификация, CSRF, CSP, Rate Limiting, Circuit Breaker)
│   ├── FRONTEND.md                 # Фронтенд (страницы, JS, UI, адаптивность, доступность)
│   ├── E2E_SCENARIOS.md            # End-to-End сценарии по ролям
│   ├── PROJECT_CONTEXT.md          # Контекст проекта
│   ├── AMVERA_CLI_AUTOMATION.md    # Автоматизация деплоя через Amvera CLI
│   ├── GITHUB_SECRETS_SETUP.md     # Настройка секретов GitHub Actions
│   └── screenshots/                # Скриншоты UI
│   # Исторические/устаревшие документы → archive/legacy_docs/
│   # (TESTING_BLUEPRINT, TEST_CHECKLIST, MIGRATION_PLAN, notifications-v2,
│   #  REFACTORING_TASKS, TRACEABILITY_MATRIX, TEST_BUTTON_REGISTRY, UX_PERFORMANCE_AUDIT)
│
├── supabase/                       # <!-- УСТАРЕЛО: Локальная конфигурация Supabase CLI — перенесена в trash/, проект на Amvera/PostgREST. Supabase НЕ используется -->
│   ├── config.toml                 # <!-- УСТАРЕЛО -->
│   └── snippets/                   # <!-- УСТАРЕЛО -->
│
├── tests/                          # Тестовая инфраструктура
│   ├── conftest.py                 # Фикстуры (preseed_test_data, class-scope сессии, admin_session)
│   ├── conftest_playwright.py      # Playwright браузерные фикстуры
│   ├── test_buttons_backend.py     # ~3200 строк комплексных тестов (Guest/Worker/Employer/Admin/Security)
│   ├── test_buttons_browser.py     # Браузерные тесты (Playwright)
│   ├── test_buttons_frontend.py    # Фронтенд-тесты кнопок
│   └── ...                         # Прочие тесты
│
├── tests_e2e/                      # End-to-end тесты (Playwright)
│
├── scripts/                        # Утилиты и скрипты
│   ├── _apply_all_direct.py        # Прямое применение всех миграций
│   ├── _create_base_tables.py      # Создание базовых таблиц
│   ├── _create_email_log.py        # Создание таблицы email_log
│   ├── _create_missing_tables.py   # Создание отсутствующих таблиц
│   ├── _init_exec_sql.py           # <!-- УСТАРЕЛО: exec_sql удалён миграцией 078_drop_exec_sql.sql -->
│   ├── preseed_test_data.py        # Предзаполнение тестовых данных
│   └── ...                         # Прочие скрипты
│
├── archive/                        # Архивные файлы (не используются)
├── plans/                          # Планы и исторические документы
└── .github/                        # GitHub Actions
```

---

## 4. Схема взаимодействия компонентов

```mermaid
flowchart TB
    User[Пользователь - браузер]

    subgraph Frontend[Фронтенд]
        Jinja2[Jinja2 Templates - 30 файлов]
        Tailwind[TailwindCSS]
        VanillaJS[Vanilla JS + PWA sw.js]
    end

    subgraph ASGI[ASGI Router - asgi.py]
        Router[RouterMiddleware]
        WS[FastAPI WebSocket Server]
        FlaskWSGI[Flask WSGIMiddleware]
    end

    subgraph FlaskApp[Flask Application]
        Factory[create_app - app/__init__.py]
        CSP[CSP + Security Headers]
        CSRF[CSRF Protection]
        ContextProc[Context Processors - 7 шт]
        Blueprints[Blueprints - ~19 модулей]
        Decorators[@login_required, @role_required]
    end

    subgraph Services[Services Layer - 13 сервисов]
        JobSvc[job_service.py]
        NotifSvc[notification_service.py]
        EmailSvc[email_service.py]
        PushSvc[push_service.py]
        RedisPub[redis_publisher.py]
    end

    subgraph CeleryLayer[Celery Tasks]
        CeleryApp[celery_app.py]
        EmailTasks[email_tasks.py]
        PushTasks[push_tasks.py]
    end

    subgraph Infrastructure[Инфраструктура]
        Redis[(Redis 8 прод / 7 локально)]
        PostgREST[(PostgREST (Amvera) - PostgreSQL)]
        SMTP[SMTP Server]
        PushAPI[Web Push API - VAPID]
    end

    User -->|HTTP| Router
    User -->|WebSocket| Router
    Router -->|HTTP| FlaskWSGI
    Router -->|WebSocket/Lifespan| WS

    FlaskWSGI --> Factory
    Factory --> CSP
    Factory --> CSRF
    Factory --> ContextProc
    Factory --> Blueprints
    Factory --> Decorators

    Blueprints --> Services
    Services -->|REST/PostgREST| PostgREST
    Services -->|Публикация событий| RedisPub

    RedisPub -->|PUBLISH| Redis

    Blueprints -->|Отправка задач| CeleryApp
    CeleryApp -->|Брокер| Redis
    CeleryApp --> EmailTasks
    CeleryApp --> PushTasks
    EmailTasks --> SMTP
    PushTasks --> PushAPI

    WS -->|Подписка/Публикация| Redis
    Redis -->|SUBSCRIBE сообщения| WS
    WS -->|Live-уведомления| User

    CeleryApp -->|Публикация результатов| RedisPub
```

---

## 5. Потоки данных

### 5.1. REST API (основной)

```
Пользователь → Flask Blueprint → Service → postgrest_client (HTTP) → PostgREST (Amvera) → PostgreSQL
```

Все CRUD-операции проходят через [`postgrest_client.py`](../app/utils/postgrest_client.py) — обёртку над HTTP-запросами к PostgREST API (Amvera) с Circuit Breaker и обработкой ошибок.

### 5.2. RPC (атомарные операции)

```
Пользователь → Flask Blueprint → postgrest_client (POST /rpc/function_name) → PostgreSQL функция
```

Ключевые RPC-функции:
- `accept_application` / `reject_application` — принятие/отклонение отклика
- `apply_job_atomic` — атомарный отклик на задание
- `delete_job_cascade` — каскадное удаление задания
- `delete_user_cascade` — каскадное удаление пользователя
- `get_job_stats` — статистика публикаций (для админ-панели)
- `nearby_jobs` — геопоиск ближайших заданий (PostGIS)

### 5.3. Загрузка файлов

```
Пользователь → Flask Blueprint → Локальное хранилище (uploads/) или Amvera Storage
```

<!-- УСТАРЕЛО: Ранее использовался Supabase Storage API → Supabase Storage Bucket -->
Используется для аватаров пользователей и изображений заданий.

### 5.4. WebSocket (чат, live-уведомления)

```
Пользователь ↔ WebSocket (asgi.py, FastAPI) ↔ Redis Pub/Sub ↔ Клиенты
```

- JWT-аутентификация WebSocket-соединений (токен генерируется в `inject_ws_config`)
- Чат-сообщения: отправка через WebSocket → сохранение в БД → публикация в Redis → доставка адресату
- Live-уведомления: Celery-задача → Redis Pub/Sub → WebSocket → браузер

### 5.5. Фоновые задачи (Celery)

```
Flask Blueprint → apply_async(task) → Redis (брокер) → Celery Worker → SMTP / Web Push API
```

**Email-задачи** ([`email_tasks.py`](../app/tasks/email_tasks.py)):
- `send_email` — отправка одного email
- `send_batch_emails` — массовая рассылка
- `send_notification_email` — уведомление на email
- `send_chat_message_email` — уведомление о новом сообщении в чате

**Push-задачи** ([`push_tasks.py`](../app/tasks/push_tasks.py)):
- `send_push_notification` — отправка Web Push уведомления
- `send_batch_push` — массовая отправка push-уведомлений

**Celery Beat** — 6 периодических задач: `drain_notification_outbox` (10с), `ensure_postgrest_role_grants` (120с), `expire_old_jobs` (1ч), `cleanup_orphaned_notifications` (1ч), `cleanup_old_email_logs` (24ч), `cleanup_expired_push_subscriptions` (1ч). Лимиты: `task_time_limit=300`, `task_soft_time_limit=240`.

### 5.6. Push-уведомления (Web Push API)

```
Celery Worker → pywebpush (VAPID) → Браузер (Service Worker) → Пользователь
```

- VAPID-ключи в [`app/config.py`](../app/config.py): `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_CLAIMS_EMAIL`
- Подписки хранятся в таблице `push_subscriptions`
- Service Worker (`sw.js`) принимает push-события и показывает браузерные уведомления

### 5.7. In-memory Mock PostgREST (тестовый режим)

```
Тесты (PyTest) → `_is_mock_enabled()` → `_test_mock_request()` → In-memory dict БД
```

В [`app/testing/mock_postgrest.py`](../app/testing/mock_postgrest.py) реализован in-memory mock для тестового режима (`TESTING=True`). Mock эмулирует:

- **PostgREST API** — GET/POST/PATCH/DELETE с фильтрацией: `eq`, `neq`, `gt`, `lt`, `ilike`, `in`, `not`, `is.null`
- **Auth RPC** — `login_user`, `register_user`
- **RPC** — `accept_application`, `reject_application`, `apply_job_atomic`, `delete_job_cascade`, `delete_user_cascade`, `get_job_stats`, `get_completed_jobs_between`, `nearby_jobs`

**Активация mock** через `_is_mock_enabled()`:
1. Переменная окружения `TESTING=True`
2. Flask-конфигурация `TESTING=True` (устанавливается в `conftest.py`)

<!-- УСТАРЕЛО: Файл `.mock_supabase` в корне проекта (legacy) удалён -->

**Защита от случайной активации:** гарда `PYTEST_CURRENT_TEST` в [`tests/conftest.py:24`](../tests/conftest.py:24) — mock активируется только при запуске через pytest.

### 5.8. Безопасность (новые улучшения)

- **Валидация email** — RFC 5322 regex в [`app/blueprints/auth.py:15`](../app/blueprints/auth.py:15)
- **Защита от SQL-инъекций** — проверка ASCII-фрагментов пользовательского ввода в [`app/blueprints/auth.py:25`](../app/blueprints/auth.py:25)
- **Дифференцированные таймауты** — GET-запросы 15s, мутации (POST/PUT/DELETE) 10s в [`postgrest_client.py`](../app/utils/postgrest_client.py)
- **PERMANENT_SESSION_LIFETIME** = 1800 секунд (30 минут)
- **JWT-аутентификация** — ДВА разных секрета: `PGRST_JWT_SECRET` (PostgREST: `role=authenticated` с `app_role=worker/employer/admin`, либо `service_role` для обхода RLS; `postgrest_admin_request` использует его для service_role-запросов) и `WEBSOCKET_JWT_SECRET` (только `user_id` + `jti`)

---

## 6. Инфраструктура и деплой

### 6.1. Конфигурация

Основные переменные окружения (из [`.env.example`](.env.example) и [`app/config.py`](../app/config.py)):

| Переменная | Назначение |
|-----------|-----------|
| `SECRET_KEY` | Секретный ключ Flask (сессии, JWT, CSRF) |
| `POSTGREST_URL` | URL PostgREST-сервиса (внутренний) |
| `PGRST_JWT_SECRET` | JWT-секрет для PostgREST |
| `DATABASE_URL` | Прямое подключение к PostgreSQL |
| `YANDEX_MAPS_API_KEY` | Ключ Яндекс.Карт |
| `REDIS_URL` | URL Redis (брокер Celery + Pub/Sub) |
| `WEBSOCKET_URL` | URL WebSocket-сервера |
| `WEBSOCKET_PORT` | Порт WebSocket (по умолчанию 8001) |
| `SMTP_HOST` / `SMTP_PORT` | SMTP-сервер для email |
| `SMTP_USER` / `SMTP_PASSWORD` | Учётные данные SMTP |
| `SMTP_FROM_EMAIL` | Отправитель email |
| `SMTP_DAILY_LIMIT` | Дневной лимит email (по умолчанию 1000) |
| `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | Ключи Web Push (VAPID) |
| `VAPID_CLAIMS_EMAIL` | Email для VAPID claims |

### 6.2. Docker Compose (локальная разработка)

Сервисы в [`docker-compose.yml`](docker-compose.yml):

| Сервис | Контейнер | Команда |
|--------|----------|---------|
| `redis` | `redis:7-alpine` | `redis-server --appendonly yes` |
| `db` | `postgis/postgis:15-3.4-alpine` | PostgreSQL 15 + PostGIS 3.4 (порт 5433→5432) |
| `postgrest` | `postgrest/postgrest:v12.2.3` | PostgREST API (порт 3000) |
| `web` | Из Dockerfile | `python app.py` (Flask dev-сервер, HTTP, порт 8000; WebSocket локально — отдельный `uvicorn asgi:application --port 8001`) |
| `celery_worker` | Из Dockerfile | `celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4` |
| `celery_beat` | Из Dockerfile | `celery -A app.tasks.celery_app beat --loglevel=info` |

### 6.3. Деплой (Amvera)

- **Платформа:** Amvera (Docker)
- **Тип:** Docker (containerPort 8000, servicePort 80)
- **Конфигурация:** [`amvera.yaml`](amvera.yaml) (docker toolchain, persistenceMount `/data`)
- **ASGI-сервер:** один процесс `uvicorn asgi:application --workers 2` (порт 8000) обслуживает И HTTP (Flask через `a2wsgi.WSGIMiddleware`), И WebSocket (`/ws`, FastAPI). Управляется supervisord вместе с `celery_worker` (`--concurrency=4`) и `celery_beat`
- **Slug:** `trudnik` (приложение), `trudnik-db` (БД)
- **Масштабирование:** определяется Amvera

### 6.4. Мониторинг

- **Health Check:** [`/health`](../app/__init__.py:361) — проверка доступности БД
- **Логирование:** стандартный Python logging
- **Git-версия:** отображается через контекст-процессор `inject_git_version`

---

> **Примечание:** Детальное описание бизнес-логики, API-маршрутов, безопасности и тестовых сценариев вынесено в соответствующие дочерние документы: [`API_REFERENCE.md`](API_REFERENCE.md), [`BUSINESS_LOGIC.md`](BUSINESS_LOGIC.md), [`SECURITY.md`](SECURITY.md), [`E2E_SCENARIOS.md`](E2E_SCENARIOS.md). (Индекс TESTING_BLUEPRINT.md перенесён в `archive/legacy_docs/` как устаревший.)
