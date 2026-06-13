# Архитектура приложения «Трудник»

**Актуально на:** 13.06.2026
**Версия документа:** 2.0 — полная переработка после удаления shifts/reviews/hires и внедрения новой state machine

---

## Оглавление

1. [Обзор системы](#1-обзор-системы)
2. [Технологический стек](#2-технологический-стек)
3. [Структура проекта](#3-структура-проекта)
4. [Архитектура бэкенда](#4-архитектура-бэкенда)
   - 4.1 [Application Factory](#41-application-factory)
   - 4.2 [Blueprint'ы (модули)](#42-blueprintы-модули)
   - 4.3 [Сервисы](#43-сервисы)
   - 4.4 [Декораторы](#44-декораторы)
   - 4.5 [Утилиты](#45-утилиты)
   - 4.6 [Контекст-процессоры](#46-контекст-процессоры)
   - 4.7 [Безопасность](#47-безопасность)
5. [Архитектура базы данных](#5-архитектура-базы-данных)
   - 5.1 [Таблицы](#51-таблицы)
   - 5.2 [Row Level Security (RLS)](#52-row-level-security-rls)
   - 5.3 [Миграции](#53-миграции)
6. [Архитектура фронтенда](#6-архитектура-фронтенда)
   - 6.1 [Шаблоны](#61-шаблоны)
   - 6.2 [JavaScript](#62-javascript)
   - 6.3 [CSS (Tailwind)](#63-css-tailwind)
   - 6.4 [PWA](#64-pwa)
   - 6.5 [UI/UX](#65-uiux)
7. [API-маршруты](#7-api-маршруты)
8. [Бизнес-процессы](#8-бизнес-процессы)
   - 8.1 [Жизненный цикл задания (State Machine)](#81-жизненный-цикл-задания-state-machine)
   - 8.2 [Жизненный цикл отклика](#82-жизненный-цикл-отклика)
   - 8.3 [Система приглашений](#83-система-приглашений)
   - 8.4 [Система оценок](#84-система-оценок)
   - 8.5 [Монетизация (платежи)](#85-монетизация-платежи)
   - 8.6 [Система уведомлений](#86-система-уведомлений)
   - 8.7 [Чат](#87-чат)
9. [Потоки данных](#9-потоки-данных)
10. [Деплой и инфраструктура](#10-деплой-и-инфраструктура)

---

## 1. Обзор системы

«Трудник» — веб-приложение (PWA) для быстрого поиска временной подработки в религиозных организациях (храмы, церкви, мечети). Две роли пользователей:

- **Работодатель (employer)** — публикует задания, управляет откликами, приглашает трудников
- **Трудник (worker)** — ищет задания, откликается, выполняет работу, получает оплату

**Модель монетизации:** плата за публикацию задания (490 ₽, 30 дней). Работодатель оплачивает размещение один раз — все контакты исполнителей видны сразу. Продление публикации — 290 ₽.

Архитектурный стиль: **монолитное Flask-приложение**, разбитое на модульные Blueprint'ы, с внешней базой данных Supabase (PostgreSQL) через REST API.

### Упрощённая модель (без shifts)

После миграций 027-028 таблицы `shifts`, `reviews`, `hires` удалены. Модель стала проще:
- **Задание** → **Отклики** → **Чат (через application_id)**
- Нет промежуточной сущности «смена» между откликом и выполнением
- Жизненный цикл задания: 5 статусов (open → in_progress → active → completed + cancelled)

---

## 2. Технологический стек

| Слой | Технология |
|------|-----------|
| **Бэкенд** | Python 3.14, Flask (Application Factory + Blueprints) |
| **База данных** | Supabase (PostgreSQL 15) — REST API + Auth + Storage |
| **Фронтенд** | HTML5, Jinja2, Tailwind CSS (CDN), Vanilla JS |
| **Карты** | Яндекс.Карты JavaScript API |
| **PWA** | Service Worker, Web App Manifest, офлайн-режим |
| **Хостинг** | Render (PaaS) — автоматический деплой из GitHub |
| **WSGI** | Gunicorn |
| **AI-помощник** | DeepSeek (веб-чат localhost:11434) |

---

## 3. Структура проекта

```
trudnik/
├── app.py                          # Точка входа: app = create_app()
├── requirements.txt                # Зависимости Python
├── render.yaml                     # Конфигурация деплоя на Render
├── .env                            # Переменные окружения (секреты)
├── .gitignore
├── PROJECT_CONTEXT.md              # Контекст проекта
├── README.md
├── generate_twa_ci.js              # Генерация Trusted Web Activity
├── tailwind.config.js              # Конфигурация Tailwind
├── twa-config.json                 # Конфигурация TWA для Google Play
├── Supabase_warnings.md            # Предупреждения Supabase
├── matrix_jobs.md                  # Матрица действий над заданиями
│
├── app/                            # Основной код приложения
│   ├── __init__.py                 # create_app() — фабрика приложения (11 blueprint'ов)
│   ├── config.py                   # Config class (загрузка из .env)
│   ├── decorators.py               # @login_required, @role_required, @csrf_protect
│   ├── utils.py                    # Утилиты: HTTP, хранилище, рейтинг, rate limit
│   ├── blueprints/
│   │   ├── __init__.py             # Реэкспорт Blueprint'ов
│   │   ├── auth.py                 # /login, /register, /logout
│   │   ├── profile.py              # /profile, /verify-employer, управление профилем
│   │   ├── jobs.py                 # /, /workers, /jobs/*, /invitations, /api/invite/*
│   │   ├── applications.py         # /apply, /my-applications, принятие/отклонение/отзыв
│   │   ├── chat.py                 # /chats, /chat/<application_id>, /api/send_message
│   │   ├── favorites.py            # /favorites, API избранного
│   │   ├── blacklist.py            # /blacklist, блокировка/разблокировка
│   │   ├── notifications.py        # /notifications, API уведомлений
│   │   ├── admin.py                # /admin, управление пользователями, верификация
│   │   ├── monetization.py         # /api/*, платежи, чеки, проверка переквалификации
│   │   └── ratings.py              # /api/ratings, создание/получение оценок
│   └── services/
│       ├── __init__.py
│       ├── notification_service.py # Сервис уведомлений (14 типов, настройки, CRUD)
│       ├── payment_service.py      # Сервис платежей (интеграция с эквайрингом)
│       └── receipt_service.py      # Сервис чеков самозанятого (ФНС)
│
├── templates/                      # Jinja2-шаблоны
│   ├── base.html                   # Базовый шаблон (шапка, нижнее меню, toast, скрипты)
│   ├── _icons.html                 # SVG-иконки (макросы Jinja2)
│   ├── _filter_skills.html         # Фильтр по навыкам (include)
│   ├── index.html                  # Лента заданий (главная)
│   ├── workers.html                # Список трудников + фильтры
│   ├── job_new.html                # Создание/редактирование задания
│   ├── job_detail.html             # Детальная страница задания
│   ├── job_publish.html            # Страница оплаты публикации
│   ├── login.html / register.html  # Аутентификация
│   ├── profile*.html               # Профили (свой, чужой, редактирование)
│   ├── my_applications.html        # Мои отклики (работодатель/трудник)
│   ├── my_jobs.html                # Мои задания (работодатель)
│   ├── favorites.html              # Избранное (трудники + задания)
│   ├── blacklist.html              # Чёрный список
│   ├── notifications.html          # Уведомления
│   ├── invitations.html            # Приглашения
│   ├── chat.html / chats_list.html # Чат и список чатов
│   ├── admin.html                  # Панель администратора
│   ├── error.html                  # Страницы ошибок (404, 500)
│   └── offline.html                # Офлайн-страница PWA
│
├── static/
│   ├── default-avatar.png
│   ├── manifest.json               # PWA Web App Manifest
│   ├── sw.js                       # Service Worker (кэширование)
│   ├── icons/                      # Иконки PWA (48-512px)
│   ├── css/
│   │   ├── tailwind.css            # Пользовательские стили Tailwind
│   │   └── tailwind.min.css        # Скомпилированный Tailwind
│   ├── js/
│   │   ├── favorites.js            # Единая функция toggleFavorite()
│   │   └── applications.js         # Логика откликов (массовые операции)
│   └── .well-known/
│       └── assetlinks.json         # Digital Asset Links (Trusted Web Activity)
│
├── migrations/                     # SQL-миграции (001-028)
├── archive/                        # Архив старых скриптов и документации
└── plans/                          # Планы и документация (.md)
```

---

## 4. Архитектура бэкенда

### 4.1 Application Factory

[`create_app()`](app/__init__.py:10) — центральная фабрика приложения. Паттерн **Application Factory** обеспечивает:

- Создание Flask-приложения с настройками из [`Config`](app/config.py:8)
- Регистрация **11** Blueprint'ов
- 5 глобальных контекст-процессоров (`context_processor`)
- Глобальный CSRF-фильтр (`before_request`)
- Регистрация API-маршрутов accept/reject/reopen на объекте `app` (вынесены из blueprint'ов из-за проблем с роутингом на Render)
- PWA-маршруты (`/offline`, `/.well-known/assetlinks.json`)
- Обработчики ошибок (404, 500)
- Кэширование Git-версии при старте

### 4.2 Blueprint'ы (модули)

| Blueprint | Файл | Маршрутов | Назначение |
|-----------|------|-----------|------------|
| `auth_bp` | [`auth.py`](app/blueprints/auth.py:8) | 3 | Логин, регистрация, выход |
| `profile_bp` | [`profile.py`](app/blueprints/profile.py) | ~10 | Профиль, верификация, загрузка фото, удаление аккаунта |
| `jobs_bp` | [`jobs.py`](app/blueprints/jobs.py) | ~30 | Задания, трудники, приглашения, поиск, force-complete, restore, cancel |
| `applications_bp` | [`applications.py`](app/blueprints/applications.py) | ~14 | Отклики, принятие/отклонение, отзыв (withdraw), массовые операции |
| `chat_bp` | [`chat.py`](app/blueprints/chat.py:7) | 7 | Список чатов, чат по application_id, отправка сообщений, удаление |
| `favorites_bp` | [`favorites.py`](app/blueprints/favorites.py:6) | 7 | Избранное (API + страница) |
| `blacklist_bp` | [`blacklist.py`](app/blueprints/blacklist.py:6) | 3 | Чёрный список |
| `notifications_bp` | [`notifications.py`](app/blueprints/notifications.py:11) | 7 | Уведомления (страница + API) |
| `admin_bp` | [`admin.py`](app/blueprints/admin.py) | ~15 | Админ-панель, управление пользователями |
| `monetization_bp` | [`monetization.py`](app/blueprints/monetization.py) | ~10 | Платежи за публикацию, чеки, проверка переквалификации |
| `ratings_bp` | [`ratings.py`](app/blueprints/ratings.py:7) | 3 | API оценок и отзывов |

**Всего: 11 blueprint'ов, ~110 маршрутов**

> **Удалён:** [`shifts_bp`](app/blueprints/shifts.py) — таблица shifts удалена (миграция 027), blueprint исключён из регистрации.

#### Ключевые модули подробнее:

**`jobs_bp`** — самый крупный модуль. Содержит:
- Главную страницу (`/`) — лента заданий с фильтрами и автопереходом in_progress→active
- [`/workers`](templates/workers.html) — список трудников с фильтрами
- `/jobs/<id>` — детальная страница задания
- `/job/new` — создание/редактирование задания (публикация сразу в `open`)
- `/my-jobs` — список заданий работодателя с массовыми действиями
- `/api/invite/<job_id>/<worker_id>` — приглашение трудника
- [`/invitations`](templates/invitations.html) — страница приглашений
- `/api/search/workers` — поиск трудников
- **`/api/jobs/<id>/force-complete`** — принудительное завершение (active/in_progress → completed)
- **`/restore-job/<id>`** — восстановление (cancelled → open)
- **`/cancel-job/<id>`** — отмена (open/in_progress → cancelled; блокировка для active)
- **`/delete-job/<id>`** — удаление с каскадным удалением связанных записей

**`chat_bp`** — чат через `application_id`:
- `/chats` — список чатов (все accepted-заявки пользователя)
- `/chat/<application_id>` — чат конкретной заявки
- `/chat/new/<worker_id>` — поиск существующего чата с работником
- `/api/send_message` — отправка сообщения (`application_id`, `sender_id`, `content`)
- `/api/messages/<application_id>/poll` — polling новых сообщений
- `/api/delete-chats` — удаление чатов (сообщений по application_id)

**`applications_bp`** — управление откликами:
- `/apply/<job_id>` — откликнуться на задание
- `/apply-selected` — массовый отклик
- `/my-applications` — страница откликов (разная для работодателя/трудника)
- **`/api/applications/<id>/withdraw`** — отзыв отклика работником (pending/accepted → withdrawn)
- `/api/applications/<id>/accept|reject|reopen` — API принятия/отклонения (вынесены на `app`)

### 4.3 Сервисы

| Сервис | Файл | Назначение |
|--------|------|------------|
| `NotificationService` | [`notification_service.py`](app/services/notification_service.py) | Типизированные уведомления (14 типов), настройки пользователя, CRUD |
| `PaymentService` | [`payment_service.py`](app/services/payment_service.py) | Обработка платежей за публикацию задания. Методы: `get_tariffs()`, `create_job_payment()`, `process_job_payment()` |
| `ReceiptService` | [`receipt_service.py`](app/services/receipt_service.py) | Формирование чеков самозанятого. Методы: `issue_receipt()`, `issue_job_publication_receipt()` |

**Типы уведомлений** (14 типов):
`application_received`, `application_accepted`, `application_rejected`, `application_cancelled`, `new_message`, `new_rating`, `job_filled`, `job_completed`, `job_cancelled`, `job_published`, `job_restored`, `hire_limit_warning`, `cheque_reminder`, `system`

> **Удалены** (после удаления shifts): `shift_checkin`, `shift_complete`, `shift_created`, `shift_reminder`, `payment_confirmed`, `payment_received`, `dispute_started`

### 4.4 Декораторы

| Декоратор | Файл | Назначение |
|-----------|------|------------|
| [`@login_required`](app/decorators.py:9) | `decorators.py` | Редирект на `/login`, если нет токена в сессии |
| [`@role_required(role)`](app/decorators.py:18) | `decorators.py` | Проверка роли через запрос к profiles |
| [`@csrf_protect`](app/decorators.py:44) | `decorators.py` | Проверка CSRF-токена для мутирующих запросов |
| `@rate_limit` | `utils.py` | Ограничение 10 POST-запросов в минуту по IP |

### 4.5 Утилиты

**[`app/utils.py`](app/utils.py)** содержит:

| Функция | Назначение |
|---------|------------|
| [`supabase_request()`](app/utils.py:66) | HTTP-запрос к Supabase REST API (с auto-refresh JWT при 401) |
| [`supabase_admin_request()`](app/utils.py:94) | Запрос с service_role_key (обход RLS для админ-операций) |
| [`refresh_access_token()`](app/utils.py:44) | Обновление JWT через refresh_token |
| [`upload_to_storage()`](app/utils.py:120) | Загрузка файла в Supabase Storage (макс. 5 MB) |
| [`add_notification()`](app/utils.py:161) | Создание уведомления (устаревшая обёртка) |
| [`update_rating()`](app/utils.py:176) | Пересчёт среднего рейтинга пользователя |
| [`calculate_distance()`](app/utils.py:33) | Формула гаверсинусов (расстояние между координатами) |
| [`copy_job()`](app/utils.py:141) | Копирование полей задания (для перепубликации) |
| [`rate_limit()`](app/utils.py:198) | Декоратор rate limiting |
| [`sanitize_postgrest()`](app/utils.py:217) | Экранирование спецсимволов PostgREST |
| [`uid()`](app/utils.py:224) | Короткий доступ к `session['user_id']` |
| [`my_query()`](app/utils.py:230) | Построитель PostgREST-запроса для текущего пользователя |

**Класс [`SupabaseResponse`](app/utils.py:20)** — типизированная обёртка над ответом Supabase REST API (`.ok`, `.status_code`, `.json()`, `.text`).

### 4.6 Контекст-процессоры

| Процессор | Переменная | Назначение |
|-----------|-----------|------------|
| `inject_global_user` | `current_user_id` | ID текущего пользователя во всех шаблонах |
| `inject_csrf_token` | `csrf_token` | CSRF-токен для форм |
| `inject_unread_notifications` | `unread_notifications` | Счётчик непрочитанных уведомлений (кэш 30с, исключает приглашения) |
| `inject_pending_invitations` | `pending_invitations` | Счётчик приглашений для трудника (кэш 30с) |
| `inject_git_version` | `git_version` | Версия коммита (кэшируется при старте) |
| `inject_application_count` | `pending_app_count` | Счётчик pending-откликов работодателя (в `jobs.py`) |
| `inject_user_role` | `current_user_role` | Роль пользователя (в `jobs.py`) |

### 4.7 Безопасность

1. **CSRF-защита** — глобальный фильтр [`before_request`](app/__init__.py:31) проверяет `X-CSRF-Token` заголовок (fetch/AJAX) или `_csrf_token` поле формы для всех мутирующих запросов. Исключения: GET/HEAD/OPTIONS, тестовый режим, `/login`, `/register`.

2. **Rate Limiting** — in-memory, per-IP: 10 POST-запросов в 60-секундном окне на маршрутах логина и регистрации.

3. **Row Level Security (Supabase)** — политики PostgreSQL ограничивают доступ к данным на уровне строк (см. раздел 5.2).

4. **JWT-токены** — хранятся в сессии Flask (`access_token`, `refresh_token`). При 401 от Supabase автоматически обновляется через `refresh_access_token()`.

5. **Валидация ввода** — `sanitize_postgrest()` экранирует спецсимволы PostgREST для предотвращения инъекций.

---

## 5. Архитектура базы данных

### 5.1 Таблицы

База данных: **Supabase (PostgreSQL 15)**

| Таблица | Назначение | Ключевые поля |
|---------|------------|---------------|
| **`profiles`** | Пользователи (расширение auth.users) | `id` (PK, FK→auth.users), `role`, `full_name`, `city`, `skills`, `religion`, `rating`, `photo_url`, `verified`, `inn`, `is_self_employed`, `desired_payment`, `experience`, `contact`, `notification_prefs`, `portfolio_link` |
| **`jobs`** | Задания | `id`, `employer_id` (FK→profiles), `organization_name`, `object_description`, `work_type`, `payment_amount`, `address`, `city`, `lat`, `lng`, `date_time`, `status` (open/in_progress/active/completed/cancelled), `max_workers`, `current_workers`, `preferred_religion`, `is_paid`, `paid_at`, `expires_at`, `tariff` |
| **`applications`** | Отклики | `id`, `job_id` (FK→jobs), `worker_id` (FK→profiles), `employer_id`, `status` (pending/accepted/rejected/withdrawn) |
| **`messages`** | Сообщения чата | `id`, `application_id` (FK→applications), `sender_id`, `content`, `created_at` |
| **`favorites`** | Избранные трудники | `user_id`, `target_id` (FK→profiles) |
| **`job_favorites`** | Избранные задания | `user_id`, `job_id` (FK→jobs) |
| **`blacklists`** | Чёрный список | `user_id`, `blocked_user_id` (FK→profiles) |
| **`ratings`** | Оценки (1-5 звёзд) | `id`, `job_id`, `rater_user_id`, `rated_user_id`, `rating_type`, `target_type`, `rating`, `comment` |
| **`notifications`** | Уведомления | `id`, `user_id`, `type`, `message`, `is_read`, `job_id`, `application_id` |
| **`invitations`** | Приглашения | `id`, `job_id`, `employer_id`, `worker_id`, `status` (pending/accepted/rejected), `message`, `created_at`, `responded_at` |
| **`job_payments`** | Платежи за публикацию | `id`, `job_id`, `employer_id`, `amount`, `tariff`, `type` (publication/renewal), `status` (pending/paid/failed), `transaction_id`, `paid_at` |
| **`tariff_settings`** | Настройки тарифов | `id`, `tariff_key`, `price`, `duration_days`, `renewal_price`, `is_active` |
| **`_archive_contact_payments`** | Архив старых платежей | Старая модель (контактные платежи, pay-per-contact) |
| **`receipts`** | Чеки самозанятого | `id`, `contact_payment_id`, `church_name`, `church_inn`, `service_description`, `amount`, `status`, `receipt_json` |
| **`monetization_settings`** | Настройки монетизации | `key`, `value` (owner_inn) |
| **`skills`** | Справочник навыков | `id`, `name`, `sort_order` |
| **`religions`** | Справочник вероисповеданий | `id`, `name`, `sort_order` |
| **`user_skills`** | Связь пользователь↔навыки | `user_id`, `skill_id` |
| **`job_photos`** | Фото заданий | `id`, `job_id`, `photo_url` |

> **Удалённые таблицы** (миграции 027-028): `shifts`, `reviews`, `hires`

### 5.2 Row Level Security (RLS)

Все таблицы с пользовательскими данными защищены RLS-политиками. Ключевые принципы:

- **Чтение (SELECT)**: большинство таблиц доступны всем авторизованным пользователям
- **Запись (INSERT)**: проверка `(SELECT auth.uid()) = owner_field`
- **Обновление (UPDATE)**: только владелец записи
- **Удаление (DELETE)**: только владелец

#### Ключевые политики (актуальное состояние после миграции 028):

**`jobs` SELECT:**
```sql
-- Видны задания в статусах open, in_progress, active, completed
-- + владелец видит свои cancelled
-- + admin видит всё
CREATE POLICY "Jobs are viewable by everyone" ON jobs
    FOR SELECT USING (
        status IN ('open', 'in_progress', 'active', 'completed')
        OR ((SELECT auth.uid()) = employer_id)
        OR (EXISTS (
            SELECT 1 FROM profiles
            WHERE profiles.id = (SELECT auth.uid()) AND profiles.role = 'admin'
        ))
    );
```

**`messages` SELECT (новая — через application_id):**
```sql
-- Видны только участникам заявки (worker_id из applications, employer_id через jobs)
CREATE POLICY "Application participants can view messages" ON messages
    FOR SELECT USING (
        (SELECT auth.uid()) IN (
            SELECT worker_id FROM applications WHERE applications.id = messages.application_id
            UNION
            SELECT jobs.employer_id FROM applications
            JOIN jobs ON jobs.id = applications.job_id
            WHERE applications.id = messages.application_id
        )
    );
```

**`messages` INSERT:**
```sql
CREATE POLICY "Application participants can insert messages" ON messages
    FOR INSERT WITH CHECK (
        (SELECT auth.uid()) = sender_id
    );
```

**`applications` SELECT:**
```sql
CREATE POLICY "Users can view own applications" ON applications
    FOR SELECT USING (
        (SELECT auth.uid()) = worker_id
        OR (SELECT auth.uid()) IN (
            SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id
        )
    );
```

**`applications` UPDATE:**
```sql
CREATE POLICY "Employers can update applications" ON applications
    FOR UPDATE USING (
        (SELECT auth.uid()) IN (
            SELECT employer_id FROM jobs WHERE jobs.id = applications.job_id
        )
    );
```

Административные операции используют `supabase_admin_request()` с `SERVICE_ROLE_KEY` для обхода RLS.

### 5.3 Миграции

Миграции в [`migrations/`](migrations/): **28 файлов (001-028)**

| # | Файл | Содержание |
|---|------|------------|
| 001 | `001_setup_rls.sql` | RLS для profiles и jobs |
| 002 | `002_apply_rls_policies.sql` | Полный набор RLS-политик для всех таблиц |
| 003 | `003_add_max_workers.sql` | Поля max_workers/current_workers, индексы |
| 004 | `004_fix_notifications.sql` | Исправления notifications |
| 005 | `005_add_is_read_column.sql` | Столбец is_read для notifications |
| 006 | `006_add_monetization.sql` | Таблицы монетизации |
| 007 | `007_add_skills_religions.sql` | Справочники навыков и вероисповеданий |
| 008 | `008_add_sort_order.sql` | Поле sort_order в справочниках |
| 009 | `009_fix_user_skills_rls.sql` | RLS для user_skills |
| 010 | `010_add_shifts_update_rls.sql` | RLS для обновления shifts (устарела) |
| 011 | `011_add_search_indexes.sql` | Поисковые индексы |
| 012 | `012_notification_prefs.sql` | Настройки уведомлений |
| 013 | `013_invitations.sql` | Таблица приглашений |
| 014 | `014_add_contact_field.sql` | Поле contact в profiles |
| 015 | `015_enable_rls_all_tables.sql` | Включение RLS для всех таблиц |
| 016 | `016_fix_supabase_warnings.sql` | Исправление предупреждений Supabase |
| 017 | `017_add_job_ratings.sql` | Таблица ratings |
| 018 | `018_fix_spatial_ref_sys_rls.sql` | RLS для spatial_ref_sys |
| 019 | `019_*.sql` (2 файла) | Доп. столбцы и фиксы безопасности |
| 020 | `020_fix_performance_warnings.sql` | Индексы производительности |
| 021 | `021_fix_performance_indexes.sql` | Дополнительные индексы |
| 022 | `022_new_monetization_model.sql` | Поля is_paid/expires_at/tariff в jobs, таблицы job_payments и tariff_settings, архивация contact_payments |
| 023 | `023_fix_job_payments_rls.sql` | Фикс RLS-политики для job_payments |
| 024 | `024_fix_rls_jobs_and_applications.sql` | Фикс RLS для jobs и applications |
| 025 | `025_fix_linter_warnings.sql` | Фикс предупреждений линтера Supabase |
| 026 | `026_fix_active_status_constraint.sql` | Добавление статуса active в CHECK constraint (для state machine) |
| 027 | `027_drop_shifts_migrate_chat.sql` | Удаление таблицы shifts, миграция чата на application_id |
| 028 | `028_sync_db_with_code.sql` | Комплексная синхронизация БД с кодом: удаление reviews/hires, обновление RLS для messages (через application_id), CHECK constraints, новые индексы |

Дополнительные скрипты:
- `FINAL_FIX.sql`, `FINAL_FIX_2.sql`, `FINAL_FIX_3.sql` — финальные исправления RLS и безопасности (поглощены миграцией 028)
- `ALL_PENDING.sql` — агрегированный скрипт всех pending-миграций

---

## 6. Архитектура фронтенда

### 6.1 Шаблоны

Все шаблоны используют **Jinja2** и расширяют [`base.html`](templates/base.html). Ключевые особенности:

- **Адаптивность**: Tailwind CSS responsive utilities (mobile-first)
- **Нижнее меню**: разное для ролей (`worker` / `employer`)
- **Иконки**: макросы Jinja2 в [`_icons.html`](templates/_icons.html) (SVG inline)
- **CSRF-токен**: скрытое поле `<input type="hidden" name="_csrf_token" value="{{ csrf_token }}">` во всех формах
- **AJAX-запросы**: заголовок `X-CSRF-Token` для обхода CSRF-проверки
- **Toast-уведомления**: JavaScript-функция `window.showToast(message, type)` в `base.html`
- **Бейджи**: `unread_notifications` (🔔 иконка), `pending_invitations` (👤+ иконка), `pending_app_count` (💼 иконка)

#### Матрица кнопок в my_jobs.html:

Для каждого задания в [`my_jobs.html`](templates/my_jobs.html) отображается набор кнопок, зависящий от статуса. В UI статусы отображаются локализованными названиями:

| Статус (технический) | Отображение в UI | Действия |
|----------------------|------------------|----------|
| **open** | «Идёт набор» | Изменить, Отменить (cancel), Дублировать, Удалить |
| **in_progress** | «Идёт набор» | Изменить, Отменить (cancel), Дублировать, Удалить |
| **active** | «Идёт набор» | Завершить (force-complete), Дублировать |
| **completed** | «Набор окончен» | Дублировать, Удалить |
| **cancelled** | «Отозвано» | Восстановить (restore), Дублировать, Удалить |

> **Локализация статусов:** технические статусы `open`, `in_progress`, `active` объединены в UI под общим отображением «Идёт набор», а `completed` отображается как «Набор окончен». Статус `cancelled` — «Отозвано».

### 6.2 JavaScript

| Файл | Содержание |
|------|------------|
| [`favorites.js`](static/js/favorites.js) | `toggleFavorite()` — единая функция для переключения избранного (оптимистичные обновления UI, откат при ошибке). `updateButtonUI()` — обновление иконки и текста кнопки |
| [`applications.js`](static/js/applications.js) | Логика массовых операций над откликами (чекбоксы, «Принять выбранные», «Отклонить выбранные») |
| Встроенные скрипты в шаблонах | `inviteWorker()` — приглашение трудника. `publishJob()` — оплата и публикация задания. `respondInvite()` — ответ на приглашение. Логика чата, оценок, удаления |

### 6.3 CSS (Tailwind)

- **Tailwind CSS v3** через CDN (Play CDN) — динамическая компиляция в браузере
- Кастомные стили в [`tailwind.min.css`](static/css/tailwind.min.css) (33 KB)
- Конфигурация в [`tailwind.config.js`](tailwind.config.js) — кастомные цвета (`primary`, `secondary`, `success`, `danger`, `warning`), шрифты, анимации
- Компонентные классы: `.app-card`, `.action-icon-btn`, `.accept-btn`, `.reject-btn`, `.contact-btn`, `.chat-btn`

### 6.4 PWA

Приложение зарегистрировано как **Progressive Web App**:

| Компонент | Файл | Описание |
|-----------|------|----------|
| **Manifest** | [`manifest.json`](static/manifest.json) | `"display": "standalone"`, иконки 48-512px, тема `#d97706` (amber-600) |
| **Service Worker** | [`sw.js`](static/sw.js) | Кэширование shell-ресурсов, стратегия Network First для HTML, Cache First для статики |
| **Офлайн** | `offline.html` | Страница-заглушка при отсутствии сети |
| **TWA** | `twa-config.json`, `generate_twa_ci.js` | Конфигурация Trusted Web Activity для Google Play |
| **Asset Links** | `.well-known/assetlinks.json` | Digital Asset Links для верификации TWA |

### 6.5 UI/UX

Описание пользовательского интерфейса ключевых страниц приложения.

#### Страница заданий для работника [`index.html`](templates/index.html)

На главной странице (лента заданий) для работника доступны три фильтра-кнопки:

| Кнопка | Назначение |
|--------|------------|
| **«Все»** | Показывает все доступные задания (статусы `open`, `in_progress`, `active`) |
| **«Новые»** | Показывает только задания, на которые работник ещё не откликался (нет отклика от текущего пользователя) |
| **«Откликнулся»** | Показывает только задания, на которые работник уже отправил отклик (статусы `pending`, `accepted`, `rejected`, `withdrawn`) |

> **Важно:** после отклика на задание оно **не пропадает** из ленты — работник может видеть его в фильтре «Откликнулся» и отслеживать статус. Задания остаются в ленте до смены статуса владельцем (force-complete / cancel).

#### Страница [`/my-jobs`](templates/my_jobs.html) для работодателя

**Локализация статусов заданий:**
- Технический статус `open` / `in_progress` / `active` → в UI отображается как **«Идёт набор»**
- Технический статус `completed` → в UI отображается как **«Набор окончен»**
- Технический статус `cancelled` → в UI отображается как **«Отозвано»**

**Фильтры на странице `/my-jobs`:**

| Фильтр | Показывает задания со статусом | Технические статусы |
|--------|-------------------------------|---------------------|
| **«Идёт набор»** | Активные задания, принимающие отклики | `open`, `in_progress`, `active` |
| **«Набор окончен»** | Завершённые задания | `completed` |
| **«Отозванные»** | Отменённые задания | `cancelled` |

> **Изменения относительно предыдущей версии:** фильтры **«В работе»** и **«Активные»** убраны. Вместо этого статусы `open`, `in_progress`, `active` объединены под общим фильтром «Идёт набор», поскольку для работодателя разделение этих трёх состояний не имеет практического смысла — во всех трёх случаях задание активно и отображается как «Идёт набор».

---

## 7. API-маршруты

Полный список API-эндпоинтов (JSON):

| Метод | Маршрут | Blueprint | Назначение |
|-------|---------|-----------|------------|
| GET | `/api/search/jobs` | jobs | Поиск заданий с фильтрами |
| GET | `/api/search/workers` | jobs | Поиск трудников |
| GET | `/api/jobs/<id>/applications` | jobs | Отклики на задание |
| POST | `/api/invite/<job_id>/<worker_id>` | jobs | Пригласить трудника |
| GET/POST | `/api/invitations` | jobs | Список/создание приглашений |
| POST | `/api/invitations/<id>/respond` | jobs | Принять/отклонить приглашение |
| POST | `/api/invitations/reject-all` | jobs | Отклонить все приглашения |
| POST | `/api/applications/<id>/accept` | app (корень) | Принять отклик |
| POST | `/api/applications/<id>/reject` | app (корень) | Отклонить отклик |
| POST | `/api/applications/<id>/reopen` | app (корень) | Переоткрыть отклик |
| POST | `/api/applications/<id>/withdraw` | applications | Отозвать отклик (pending/accepted → withdrawn) |
| POST | `/api/favorites/add` | favorites | Добавить в избранное |
| POST | `/api/favorites/remove` | favorites | Удалить из избранного |
| POST | `/api/favorites/check` | favorites | Проверить статус избранного |
| POST | `/api/favorites/remove-selected` | favorites | Массовое удаление |
| POST | `/api/send_message` | chat | Отправить сообщение (через application_id) |
| GET | `/api/messages/<application_id>/poll` | chat | Polling новых сообщений |
| POST | `/api/delete-chats` | chat | Удалить чаты |
| GET | `/api/notifications` | notifications | Список уведомлений (пагинация) |
| GET | `/api/notifications/unread-count` | notifications | Счётчик непрочитанных |
| POST | `/api/notifications/read-all` | notifications | Пометить все прочитанными |
| POST | `/api/notifications/<id>/delete` | notifications | Удалить уведомление |
| POST | `/api/notifications/delete-all` | notifications | Удалить все |
| POST | `/api/jobs/<id>/publish` | jobs | Оплатить и опубликовать задание |
| POST | `/api/jobs/<id>/renew` | jobs | Продлить публикацию на 30 дней |
| **POST** | **`/api/jobs/<id>/force-complete`** | **jobs** | **Принудительно завершить задание (active/in_progress → completed)** |
| GET/POST | `/restore-job/<id>` | jobs | Восстановить отменённое задание (cancelled → open) |
| GET/POST | `/cancel-job/<id>` | jobs | Отменить задание (open/in_progress → cancelled) |
| GET | `/api/admin/job-stats` | monetization | Статистика по публикациям |
| GET | `/api/ratings/<job_id>` | ratings | Оценки задания |
| GET | `/api/ratings/user/<user_id>` | ratings | Рейтинг пользователя |
| POST | `/api/ratings` | ratings | Создать/обновить оценку |
| GET/POST | `/api/monetization/*` | monetization | Настройки и платежи |
| POST | `/api/skills` | admin | Управление навыками (админ) |
| POST | `/api/religions` | admin | Управление вероисповеданиями (админ) |

---

## 8. Бизнес-процессы

### 8.1 Жизненный цикл задания (State Machine)

```
                          ┌──────────────────────────────────────────────┐
                          │                                              │
                          ▼                                              │
┌──────┐   оплата    ┌──────┐   принят    ┌─────────────┐   date_time   ┌────────┐
│draft │────────────▶│ open │──отклик────▶│ in_progress │──наступило────▶│ active │
│  ✗   │            │      │             │             │               │        │
└──────┘            └──┬───┘             └──────┬──────┘               └───┬────┘
                      │                        │                          │
                      │       cancel_job        │      force-complete      │
                      └──────────┬─────────────┴────────────┬─────────────┘
                                 │                          │
                                 ▼                          ▼
                           ┌──────────┐              ┌───────────┐
                           │ cancelled│              │ completed │
                           └────┬─────┘              └───────────┘
                                │
                                │ restore_job
                                ▼
                           ┌──────┐
                           │ open │
                           └──────┘
```

> **Примечание:** `draft` исключён из CHECK constraint`а (миграция 028). Задание публикуется сразу в `open` с `is_paid=true`. Статус `draft` сохранён на диаграмме для иллюстрации потока создания, но в коде не используется.

**5 статусов задания:**

| Статус | Описание | Видимость |
|--------|----------|-----------|
| **`open`** | Опубликовано и оплачено (is_paid=true, expires_at=now+30d). Принимаются отклики. | Всем |
| **`in_progress`** | Есть принятые отклики (current_workers > 0). | Всем |
| **`active`** | Дата задания наступила (date_time ≤ now). Автопереход из in_progress. Работа выполняется. | Всем |
| **`completed`** | Завершено (force-complete работодателем). | Всем |
| **`cancelled`** | Отменено работодателем. | Только владельцу |

**Правила переходов:**

| Из | В | Условие | Механизм |
|----|---|---------|----------|
| `(создание)` | `open` | Оплата через `POST /api/jobs/<id>/publish` | `PaymentService.process_job_payment()` |
| `open` | `in_progress` | Принят первый отклик (current_workers > 0) | `api_handle_application('accept')` |
| `in_progress` | `active` | `date_time <= now()` | `_auto_transition_in_progress_to_active()` — вызывается при каждом просмотре |
| `in_progress` | `completed` | Ручное завершение | `POST /api/jobs/<id>/force-complete` |
| `active` | `completed` | Ручное завершение | `POST /api/jobs/<id>/force-complete` |
| `open` | `cancelled` | Отмена работодателем | `POST /cancel-job/<id>` |
| `in_progress` | `cancelled` | Отмена работодателем | `POST /cancel-job/<id>` |
| `cancelled` | `open` | Восстановление | `POST /restore-job/<id>` — сбрасывает accepted в rejected, current_workers=0 |

**Блокировки:**
- Нельзя отменить `active` задание — только `force-complete`
- При восстановлении все accepted-заявки сбрасываются в rejected

### 8.2 Жизненный цикл отклика

```
                  ┌──────────┐
                  │ pending  │──отзыв────▶ withdrawn
                  └────┬─────┘
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
        accepted   rejected   withdrawn
            │
            │ отзыв
            ▼
        withdrawn
```

**4 статуса отклика:**

| Статус | Описание |
|--------|----------|
| **`pending`** | Ожидает решения работодателя |
| **`accepted`** | Принят работодателем |
| **`rejected`** | Отклонён работодателем |
| **`withdrawn`** | Отозван трудником (заменяет старый `cancelled`) |

**Переходы:**
- `pending` → `accepted`: `POST /api/applications/<id>/accept` (работодатель)
- `pending` → `rejected`: `POST /api/applications/<id>/reject` (работодатель)
- `rejected` → `pending`: `POST /api/applications/<id>/reopen` (работодатель)
- `pending` → `withdrawn`: `POST /api/applications/<id>/withdraw` (трудник)
- `accepted` → `withdrawn`: `POST /api/applications/<id>/withdraw` (трудник)

### 8.3 Система приглашений

Работодатель может **пригласить** трудника на конкретное задание:

1. Работодатель нажимает «Пригласить» на странице [`/workers`](templates/workers.html) или [`/favorites`](templates/favorites.html)
2. Вводит ID задания через `prompt()`
3. `POST /api/invite/<job_id>/<worker_id>` — создаёт запись в `invitations` (статус `pending`)
4. Трудник получает уведомление-приглашение (отображается на 👤+ иконке, отдельно от основных уведомлений)
5. Трудник может **принять** или **отклонить** приглашение на [`/invitations`](templates/invitations.html)
6. При принятии создаётся отклик со статусом `accepted`

**Кросс-страничная синхронизация**: при загрузке любой страницы бэкенд проверяет существующие приглашения и отображает «✓ Приглашён» для уже приглашённых трудников.

### 8.4 Система оценок

После завершения задания (статус `completed`):

1. Обе стороны могут выставить оценку 1-5 звёзд + комментарий
2. `POST /api/ratings` — UPSERT: одна оценка на пару (rater, job_id)
3. `update_rating()` пересчитывает средний рейтинг пользователя

**Ограничения:**
- Нельзя оценить самого себя
- Только для завершённых заданий (статус `completed`)
- Тип оценки: `worker` (работодатель→трудник) или `employer` (трудник→работодатель)

### 8.5 Монетизация (платежи)

Модель: **плата за публикацию задания**.

1. Работодатель заполняет форму задания — сохраняется сразу в `open` с `is_paid=false`
2. Редирект на страницу оплаты [`job_publish.html`](templates/job_publish.html) с ценой тарифа (490 ₽)
3. Кнопка «Оплатить 490 ₽» — `POST /api/jobs/<id>/publish`
4. `PaymentService.create_job_payment()` — создаёт запись `job_payments` (статус `pending`)
5. `PaymentService.process_job_payment()` — эмуляция эквайринга → статус `paid`
    - Задание: `is_paid=true`, `expires_at=now+30d`
    - Чек через `ReceiptService.issue_job_publication_receipt()`
    - Уведомление «Задание опубликовано» (`job_published`)
6. **Продление**: `POST /api/jobs/<id>/renew` — оплата 290 ₽ → `expires_at += 30d`

**Настройки** в `tariff_settings`: `tariff_key='standard'`, `price=490`, `duration_days=30`, `renewal_price=290`. `monetization_settings` хранит `owner_inn` для чеков.

**Старая модель** (pay-per-contact) полностью удалена: таблица `contact_payments` заархивирована как `_archive_contact_payments`, paywall из откликов убран (миграция 022).

### 8.6 Система уведомлений

- **14 типов уведомлений** (см. [`NOTIFICATION_TYPES`](app/services/notification_service.py:8))
- **Настройки пользователя**: поле `notification_prefs` (JSON) в `profiles` — можно отключить отдельные типы
- **Создание**: через `create()` (сервис) или `add_notification()` (утилита)
- **Кэширование**: счётчик непрочитанных кэшируется в сессии на 30 секунд (исключает приглашения)
- **Очистка**: уведомления-приглашения с удалёнными заданиями автоматически удаляются при просмотре

**Актуальные типы:**

| Ключ | Название | Триггер |
|------|----------|---------|
| `application_received` | Новый отклик | Трудник откликнулся |
| `application_accepted` | Отклик принят | Работодатель принял |
| `application_rejected` | Отклик отклонён | Работодатель отклонил |
| `application_cancelled` | Отклик отменён | Отклик отменён |
| `new_message` | Новое сообщение | Сообщение в чате |
| `new_rating` | Новая оценка | Получена оценка |
| `job_filled` | Задание укомплектовано | current_workers = max_workers |
| `job_completed` | Задание завершено | force-complete |
| `job_cancelled` | Задание отменено | cancel |
| `job_published` | Задание опубликовано | Успешная оплата публикации |
| `job_restored` | Задание восстановлено | restore |
| `hire_limit_warning` | Предупреждение | Лимит наймов |
| `cheque_reminder` | Напоминание о чеке | Напоминание самозанятому |
| `system` | Системное | Системные события |

### 8.7 Чат

- Чат привязан к **заявке** (`applications.id`), а не к заданию
- Каждая accepted-заявка = один чат между работодателем и трудником
- **Список чатов**: `/chats` — все accepted-заявки пользователя
- **Отправка**: `POST /api/send_message` → `messages` (с `application_id`) + уведомление получателю
- **Polling**: `GET /api/messages/<application_id>/poll?since_id=X` — получение новых сообщений
- **Удаление**: `POST /api/delete-chats` — удаление сообщений чата по `application_id`

---

## 9. Потоки данных

### Регистрация пользователя

```
[Форма регистрации] → POST /register
  → Supabase Auth: POST /auth/v1/signup (создание auth.users)
  → Supabase REST: PATCH /profiles (service_role: обновление профиля)
  → Supabase REST: POST /user_skills (связь с навыками)
  → Редирект на /login
```

### Логин

```
[Форма логина] → POST /login
  → Supabase Auth: POST /auth/v1/token?grant_type=password
  → Supabase REST: GET /profiles (получение роли)
  → session['access_token'], session['refresh_token'], session['user_id'], session['role']
  → Редирект: employer → /my-jobs, worker → /
```

### Создание и публикация задания

```
[Форма] → POST /job/new
  → Валидация стоп-слов
  → Supabase REST: POST /jobs (status='open', is_paid=false)
  → Supabase Storage: POST /storage/v1/object/photo/ (загрузка фото)
  → Редирект на /job/<id>/publish

[Страница оплаты] → POST /api/jobs/<id>/publish
  → PaymentService.create_job_payment() → job_payments (pending)
  → PaymentService.process_job_payment() → эмуляция оплаты
  → Supabase REST: PATCH /jobs (is_paid=true, expires_at=now+30d)
  → ReceiptService.issue_job_publication_receipt() → receipts
  → NotificationService.create() → уведомление job_published
  → Редирект на /my-jobs
```

### Приглашение трудника

```
[Кнопка «Пригласить»] → inviteWorker()
  → prompt("Введите ID задания")
  → POST /api/invite/<job_id>/<worker_id>
    → Проверка владельца задания (_check_job_owner)
    → Проверка дубликата приглашения
    → Проверка свободных мест
    → Supabase REST: POST /invitations
    → NotificationService.create() — уведомление труднику
  → JS: кнопка меняется на «✓ Приглашён» (disabled)
```

### Force-complete (принудительное завершение)

```
POST /api/jobs/<id>/force-complete
  → Проверка владельца и статуса (active/in_progress)
  → Массовое отклонение pending-откликов
  → PATCH jobs: status='completed'
  → Уведомление всех accepted-работников (job_completed)
```

### Восстановление задания

```
POST /restore-job/<id>
  → Проверка статуса (только cancelled)
  → Сброс accepted-заявок в rejected
  → Обнуление current_workers
  → PATCH jobs: status='open', current_workers=0
  → Уведомление rejected-заявителей (job_restored)
```

### Отзыв отклика

```
POST /api/applications/<id>/withdraw
  → Проверка авторства (только свой отклик)
  → Проверка статуса (pending или accepted)
  → PATCH applications: status='withdrawn'
  → Уменьшение current_workers (если был accepted)
  → Проверка автоперехода задания in_progress→open (если current_workers=0)
```

### Оценка

```
POST /api/ratings {job_id, rated_user_id, rating, comment, target_type}
  → Валидация (rating 1-5, target_type, не сам себе)
  → Проверка статуса задания (completed)
  → UPSERT: INSERT или PATCH (если уже есть оценка)
  → update_rating() — пересчёт среднего рейтинга
```

---

## 10. Деплой и инфраструктура

### Хостинг: Render

- **Платформа**: [Render](https://dashboard.render.com) (PaaS)
- **Runtime**: Python 3
- **Build**: `pip install -r requirements.txt`
- **Start**: `gunicorn app:app --bind 0.0.0.0:$PORT`
- **Деплой**: автоматический при `git push` в ветку `main`
- **Конфигурация**: [`render.yaml`](render.yaml)

### База данных: Supabase

- **Тип**: PostgreSQL 15 (managed)
- **API**: REST (PostgREST), Auth (GoTrue), Storage (S3-совместимый)
- **RLS**: Row Level Security для всех пользовательских таблиц
- **Миграции**: ручное применение SQL-скриптов из `migrations/`

### Переменные окружения

| Переменная | Назначение |
|-----------|------------|
| `SECRET_KEY` | Секретный ключ Flask (сессии, CSRF) |
| `SUPABASE_URL` | URL Supabase-проекта |
| `SUPABASE_ANON_KEY` | Анонимный ключ Supabase (публичный API) |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role ключ (обход RLS, админ-операции) |
| `YANDEX_MAPS_API_KEY` | Ключ Яндекс.Карт |
| `PORT` | Порт (устанавливается Render автоматически) |

### PWA / Google Play

- **PWA**: Service Worker + Manifest → устанавливается как standalone-приложение
- **TWA**: Trusted Web Activity для публикации в Google Play
- **Генерация APK**: `generate_twa_ci.js` + Bubblewrap CLI

---

## Приложение: Сводная таблица Blueprint'ов

| # | Blueprint | Файл | Маршрутов | Основные URL |
|---|-----------|------|-----------|-------------|
| 1 | `auth_bp` | `auth.py` | 3 | `/login`, `/register`, `/logout` |
| 2 | `profile_bp` | `profile.py` | ~10 | `/profile`, `/profile/<id>`, `/profile/update`, `/verify-employer` |
| 3 | `jobs_bp` | `jobs.py` | ~30 | `/`, `/workers`, `/jobs/<id>`, `/job/new`, `/my-jobs`, `/invitations`, `/api/invite/*`, `/api/jobs/<id>/force-complete`, `/restore-job/<id>`, `/cancel-job/<id>` |
| 4 | `applications_bp` | `applications.py` | ~14 | `/apply`, `/my-applications`, `/api/applications/<id>/withdraw` |
| 5 | `chat_bp` | `chat.py` | 7 | `/chats`, `/chat/<application_id>`, `/api/send_message`, `/api/messages/<application_id>/poll`, `/api/delete-chats` |
| 6 | `favorites_bp` | `favorites.py` | 7 | `/favorites`, `/api/favorites/*` |
| 7 | `blacklist_bp` | `blacklist.py` | 3 | `/blacklist`, `/unblock/<id>` |
| 8 | `notifications_bp` | `notifications.py` | 7 | `/notifications`, `/api/notifications/*` |
| 9 | `admin_bp` | `admin.py` | ~15 | `/admin`, управление пользователями, навыками, верификациями |
| 10 | `monetization_bp` | `monetization.py` | ~10 | `/api/*`, платежи, чеки, настройки |
| 11 | `ratings_bp` | `ratings.py` | 3 | `/api/ratings`, `/api/ratings/user/<id>` |

**Корневые маршруты (на app):**
- `POST /api/applications/<id>/accept|reject|reopen`
- `GET /offline`
- `GET /.well-known/assetlinks.json`

**Изменения относительно предыдущей версии:**
- ❌ `shifts_bp` — удалён (таблица shifts удалена, миграция 027)
- ❌ Таблицы `reviews`, `hires` — удалены (миграция 028)
- ✅ `withdraw` — новый статус отклика (заменяет `cancelled`)
- ✅ `force-complete` — новый маршрут принудительного завершения
- ✅ `restore` — восстановление отменённого задания
- ✅ Чат через `application_id` вместо `shift_id`
- ✅ 5 статусов заданий вместо 7 (убраны `draft`, `paid`, `expired`)
- ✅ 14 типов уведомлений вместо 18
- ✅ 28 миграций (001-028)

---

*Документ сгенерирован на основе анализа исходного кода 13.06.2026. Версия 2.1 — добавлен раздел UI/UX, обновлена матрица кнопок my_jobs.html.*
