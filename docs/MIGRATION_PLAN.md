# План миграции проекта «Трудник» с Supabase на российский облачный сервис

**Дата:** 19 июня 2026  
**Версия:** 1.0  
**Статус:** Проект  

---

## Содержание

1. [Сравнение и выбор российского провайдера](#1-сравнение-и-выбор-российского-провайдера)
2. [Инвентаризация затрагиваемых файлов](#2-инвентаризация-затрагиваемых-файлов)
3. [Пошаговый план миграции](#3-пошаговый-план-миграции-этапы)
4. [Стратегия замены Supabase Auth](#4-стратегия-замены-supabase-auth)
5. [Стратегия замены PostgREST API](#5-стратегия-замены-postgrest-api)
6. [Стратегия миграции RLS и PostgreSQL-функций](#6-стратегия-миграции-rls-и-postgresql-функций)
7. [Стратегия замены Storage](#7-стратегия-замены-storage)
8. [Риски и план отката](#8-риски-и-план-отката-rollback)
9. [Оценка трудозатрат](#9-оценка-трудозатрат)
10. [Приложения](#10-приложения)

---

## 1. Сравнение и выбор российского провайдера

### 1.1. Критерии сравнения

| Критерий | Вес | Описание |
|----------|-----|----------|
| Managed PostgreSQL (с PostGIS) | Критический | Полноценный managed Postgres с поддержкой расширений: PostGIS (гео-поиск), pgcrypto (UUID), pg_trgm (текстовый поиск) |
| Docker-контейнеры | Критический | Возможность деплоя Docker-образов (Flask + FastAPI + Celery) |
| S3-совместимое хранилище | Критический | Замена Supabase Storage для аватаров и фото заданий |
| ЦОД на территории РФ | Критический | Сертификация 152-ФЗ, хранение персональных данных на территории РФ |
| Managed Redis или свой контейнер | Высокий | Для Celery-брокера + Pub/Sub (WebSocket-уведомления) |
| SSL/домены из коробки | Высокий | Автоматический HTTPS, кастомный домен |
| Простота деплоя | Средний | CI/CD, CLI-инструменты, git-интеграция |
| Цена (для небольшого проекта) | Средний | Приемлемая стоимость для стартапа / небольшого проекта |

### 1.2. Сравнительная таблица провайдеров

| Характеристика | Яндекс Облако | VK Cloud | Selectel | SberCloud | Amvera | Beget |
|---------------|---------------|----------|----------|-----------|--------|-------|
| **Managed PostgreSQL** | Да (Managed Service for PostgreSQL) | Да (DBaaS) | Да (Облачные базы данных) | Да (CS DBaaS) | Да (встроенный Postgres) | Да (managed, от 800 ₽/мес) |
| **PostGIS** | Да | Да | Да | Да | Требует уточнения | Да |
| **Docker-контейнеры** | Да (Serverless Containers / Managed K8s) | Да (K8s Cluster / Cloud Containers) | Да (Облачные контейнеры) | Да (SberCloud Containers) | **Да (нативная платформа)** | Только на VPS (ручная установка) |
| **S3-хранилище** | Да (Object Storage) | Да (Cloud Storage) | Да (S3 Object Storage) | Да (CS Object Storage) | Да (встроенное S3) | Нет (нужен Яндекс Object Storage) |
| **ЦОД в РФ** | Да (Москва, Владимир) | Да (Москва, СПб) | Да (Москва, СПб) | Да (Москва) | Да (Москва) | Да (Москва, СПб) |
| **152-ФЗ** | Да (аттестат ФСТЭК) | Да | Да | Да (аттестован) | В процессе | **Да (аттестован)** |
| **Managed Redis** | Да | Да | Да (in-memory DB) | Да | Свой контейнер | Нет (свой контейнер на VPS) |
| **SSL/домены** | Да (Certificate Manager) | Да | Да | Да | **Да (автоматически)** | Ручная настройка (Let's Encrypt) |
| **CI/CD** | GitLab CI, GitHub Actions | GitLab CI | Встроенный CI/CD | GitLab CI | **Push-to-deploy (git push)** | Нет (ручная настройка) |
| **Простота деплоя** | Средняя (сложная документация) | Средняя | Средняя | Средняя | **Высокая (один push)** | Низкая (ручная настройка всех сервисов) |
| **Минимальная цена/мес** | ~3 500 ₽ (БД 2 vCPU + контейнеры + S3) | ~3 000 ₽ | ~3 500 ₽ | ~4 000 ₽ | **~700 ₽ (начальный тариф)** | ~400 ₽ (VPS) + ~800 ₽ (БД) + ~150 ₽ (S3) = ~1 350 ₽ |
| **Бесплатный trial** | Да (грант 4000 ₽) | Да (30 дней) | Да (3000 ₽ бонус) | Да | Да (тестовый период) | Да (30 дней VPS) |
| **Python-экосистема** | Средняя | Средняя | Средняя | Средняя | **Отличная (специализация на Python)** | Низкая (исторически PHP-хостинг) |
| **Совместимость с существующей конфигурацией** | Низкая (требует адаптации) | Низкая | Низкая | Низкая | **Высокая (уже есть .env.amvera, WORKER_SITE_URL)** | Низкая (всё с нуля) |

### 1.3. Рекомендованный выбор: **Amvera** (приоритет №1)

**Обоснование:**

1. **Существующая интеграция.** Проект уже имеет:
   - Файл [`.env.amvera`](.env.amvera) с настроенными переменными окружения
   - `WORKER_SITE_URL=https://trudnik-hyperstls.amvera.io/` в [`app/config.py:17`](app/config.py:17) — домен уже на Amvera
   - [`Dockerfile:6-11`](Dockerfile:6) содержит Amvera-совместимые директивы (`/data` volume)
   - [`render.yaml`](render.yaml) и [`docker-compose.yml`](docker-compose.yml) — нужно будет мигрировать, но основа готова

2. **Цена.** Начальный тариф ~700 ₽/мес — в 5 раз дешевле конкурентов. Все сервисы (БД, Redis, PostgREST, S3, SSL) включены в стоимость. Для небольшого религиозного проекта это критично.

3. **Простота деплоя.** Push-to-deploy — `git push amvera master` — без сложной настройки K8s, без ручного CI/CD.

4. **Python-специализация.** Amvera заточена под Python-проекты, Flask/FastAPI из коробки. В отличие от Beget (исторически PHP-хостинг) и универсальных облачных провайдеров.

5. **Встроенный S3.** Не нужно отдельно настраивать Object Storage и платить за него.

6. **Автоматические SSL и домены.** HTTPS из коробки, не нужен Certbot (в отличие от Beget, где требуется ручная настройка Let's Encrypt).

7. **Микросервисы из коробки.** 6 контейнеров (Flask, WebSocket, PostgREST, Celery Worker, Celery Beat, Redis) работают как сервисы одного проекта в docker-compose.

**Почему НЕ Beget:**

Beget — традиционный хостинг/VPS-провайдер, который **не подходит** для этого проекта по ключевым причинам:
- ❌ **Нет нативной поддержки Docker.** Все 6 контейнеров пришлось бы разворачивать вручную на VPS, настраивать сети, мониторинг и перезапуски.
- ❌ **Нет S3-хранилища.** Нужен сторонний сервис (Яндекс Object Storage, +150 ₽/мес).
- ❌ **Нет CI/CD.** Каждый деплой — ручная работа: rsync, docker-compose pull/up, перезапуск.
- ❌ **Нет managed Redis.** Пришлось бы поднимать свой контейнер на VPS.
- ❌ **PHP-ориентированный.** Python поддерживается только на VPS, без специализированных инструментов.
- ❌ **Реальная цена выше.** VPS (~400 ₽) + managed PostgreSQL (~800 ₽) + S3-аналог (~150 ₽) = минимум ~1 350 ₽/мес, почти в 2 раза дороже Amvera.

Beget может рассматриваться только если критически требуется **готовая сертификация 152-ФЗ прямо сейчас** и при этом Amvera по каким-то причинам недоступна.

**Риски Amvera:**
- Не полностью управляемый Postgres (возможно, придётся поднимать свой контейнер)
- Меньше возможностей масштабирования по сравнению с K8s-решениями
- Статус 152-ФЗ сертификации требует уточнения

**План «Б»:** Если Amvera не подойдёт по техническим причинам — **Яндекс Облако** (Managed PostgreSQL + Serverless Containers).
**План «В»:** Если критичен 152-ФЗ и нужен именно managed PostgreSQL — **Beget** (только при условии, что проект свёрнут с Docker на монолитную архитектуру).

---

## 2. Инвентаризация затрагиваемых файлов

### 2.1. Критические изменения (полная переработка)

| Файл | Тип изменений | Сложность | Строки |
|------|---------------|-----------|--------|
| [`app/utils.py`](app/utils.py) | Замена всех `supabase_request()`, `supabase_admin_request()`, `supabase_rpc()`, `upload_to_storage()`, `refresh_access_token()` на работу с self-hosted PostgREST + S3 | **Высокая** | 158-512 |
| [`app/blueprints/auth.py`](app/blueprints/auth.py) | Полная замена GoTrue Auth на Flask-Login + bcrypt + PyJWT | **Высокая** | 1-177 |
| [`app/config.py`](app/config.py) | Замена `SUPABASE_*` на `POSTGREST_URL`, `JWT_SECRET`, `S3_*`, `DATABASE_URL` | **Средняя** | 13-17 |

### 2.2. Значительные изменения (замена URL/адаптация)

| Файл | Тип изменений | Сложность | Строки |
|------|---------------|-----------|--------|
| [`app/__init__.py`](app/__init__.py) | Обновление CSP-заголовков (connect-src), замена supabase-доменов на свои | **Средняя** | 48-55 |
| [`app/blueprints/profile.py`](app/blueprints/profile.py) | Замена `upload_to_storage()` + адаптация change-password/delete-account | **Средняя** | 93, 127, 134, 162 |
| [`docker-compose.yml`](docker-compose.yml) | Добавление сервиса postgrest, замена `SUPABASE_*` env на `DATABASE_URL` + `POSTGREST_URL` | **Средняя** | 1-74 |
| [`Dockerfile`](Dockerfile) | Добавление postgrest binary или multi-stage build | **Средняя** | 1-38 |
| [`render.yaml`](render.yaml) | Замена env-переменных, возможно удаление (если полный переход на Amvera) | **Средняя** | 1-21 |
| [`.env.example`](.env.example) | Полная ревизия переменных окружения | **Средняя** | 1-42 |
| [`.env.amvera`](.env.amvera) | Обновление всех значений на новые | **Средняя** | 1-45 |

### 2.3. Умеренные изменения (адаптация)

| Файл | Тип изменений | Сложность | Комментарий |
|------|---------------|-----------|-------------|
| [`app/tasks/celery_app.py`](app/tasks/celery_app.py) | Замена импортов и env-переменных в конфигурации Celery | **Низкая** | Только `DATABASE_URL` |
| [`app/tasks/email_tasks.py`](app/tasks/email_tasks.py) | Замена `supabase_admin_request` → прямые запросы к БД/PostgREST | **Низкая** | Отдельные вызовы |
| [`app/tasks/push_tasks.py`](app/tasks/push_tasks.py) | Замена `supabase_admin_request` | **Низкая** | Отдельные вызовы |
| [`app/services/job_service.py`](app/services/job_service.py) | Замена `supabase_request`/`supabase_admin_request` | **Средняя** | Множественные вызовы |
| [`app/services/notification_service.py`](app/services/notification_service.py) | Замена `supabase_admin_request` | **Средняя** | Множественные вызовы |
| [`app/blueprints/admin.py`](app/blueprints/admin.py) | Замена `supabase_admin_request` → PostgREST admin | **Средняя** | Админ-панель |
| [`app/blueprints/jobs.py`](app/blueprints/jobs.py) | Замена `supabase_request`/`supabase_admin_request` | **Средняя** | Множественные CRUD-операции |
| [`app/blueprints/jobs_api.py`](app/blueprints/jobs_api.py) | Замена `supabase_request`/`supabase_admin_request` | **Средняя** | API-эндпоинты |
| [`app/blueprints/applications.py`](app/blueprints/applications.py) | Замена `supabase_request`/`supabase_admin_request`/`supabase_rpc` | **Средняя** | Бизнес-логика откликов |
| [`app/blueprints/chat.py`](app/blueprints/chat.py) | Замена `supabase_request` | **Низкая** | CRUD сообщений |
| [`app/blueprints/favorites.py`](app/blueprints/favorites.py) | Замена `supabase_request` | **Низкая** | CRUD избранного |
| [`app/blueprints/blacklist.py`](app/blueprints/blacklist.py) | Замена `supabase_request` | **Низкая** | CRUD чёрного списка |
| [`app/blueprints/notifications.py`](app/blueprints/notifications.py) | Замена `supabase_request` | **Низкая** | CRUD уведомлений |
| [`app/blueprints/ratings.py`](app/blueprints/ratings.py) | Замена `supabase_request`/`supabase_admin_request` | **Низкая** | Рейтинги |
| [`app/blueprints/employers.py`](app/blueprints/employers.py) | Замена `supabase_request` | **Низкая** | Поиск работодателей |
| [`app/blueprints/seo.py`](app/blueprints/seo.py) | Без изменений | **Нулевая** | Статические страницы |

### 2.4. Миграции БД

| Группа файлов | Тип изменений | Сложность |
|---------------|---------------|-----------|
| `migrations/001-048` (48 файлов) | Замена `auth.uid()` → `current_setting('request.jwt.claim.sub')` или `request.jwt.claim.user_id` | **Высокая** |

### 2.5. Статические файлы и шаблоны

| Группа файлов | Тип изменений | Сложность |
|---------------|---------------|-----------|
| `static/sw.js` | Обновление URL кэширования (если меняются домены статики) | **Низкая** |
| `templates/base.html` | Проверка CSP-совместимости, инлайн-скрипты | **Низкая** |
| Все шаблоны Jinja2 | Проверка, что URL аватаров/фото обновляются через новые хелперы | **Низкая** |

### 2.6. Инфраструктурные файлы

| Файл | Тип изменений | Сложность |
|------|---------------|-----------|
| [`asgi.py`](asgi.py) | Без изменений | **Нулевая** |
| [`requirements.txt`](requirements.txt) | Добавить: `psycopg2-binary`, `bcrypt`, `boto3`; удалить: `supabase` | **Низкая** |
| [`requirements-dev.txt`](requirements-dev.txt) | Аналогично requirements.txt | **Низкая** |
| [`scripts/apply_migrations.py`](scripts/apply_migrations.py) | Адаптировать под новую БД (прямое подключение psycopg2) | **Средняя** |

### 2.7. Сводка по сложности

| Сложность | Количество файлов |
|-----------|-------------------|
| Высокая | 3 (`utils.py`, `auth.py`, 48 migration files) |
| Средняя | 14 |
| Низкая | 15+ |
| Нулевая | 2 |

---

## 3. Пошаговый план миграции (этапы)

```mermaid
flowchart TD
    A[Этап 0: Подготовка] --> B[Этап 1: Инфраструктура]
    B --> C[Этап 2: База данных]
    C --> D[Этап 3: Аутентификация]
    D --> E[Этап 4: Бэкенд]
    E --> F[Этап 5: Фронтенд и CSP]
    F --> G[Этап 6: Тестирование]
    G --> H{Успешно?}
    H -->|Да| I[Этап 7: Переключение]
    H -->|Нет| J[Откат]
```

### Этап 0: Подготовка

**Продолжительность:** 1 день
**Риски:** Низкие
**Критерии приёмки:** Полный бэкап Supabase, экспортированные данные, создан feature-ветка `migration/russia-cloud`, подтверждена техническая совместимость Amvera

| Шаг | Описание |
|-----|----------|
| 0.0 | **Уточнить у поддержки Amvera:** доступность managed PostgreSQL (v15) с расширениями PostGIS, pgcrypto, pg_trgm; возможность запуска контейнера PostgREST `postgrest/postgrest:v12`; лимиты тарифа «Базовый» на количество контейнеров. Создать тестовый проект для проверки |
| 0.1 | Создать полный бэкап Supabase: `pg_dump` через connection string (порт 6543 — pooler) |
| 0.2 | Экспортировать `auth.users` через Supabase Dashboard (SQL Editor) с помощью `auth.raw_user_meta_data()` |
| 0.3 | Сохранить бэкап в защищённое облачное хранилище (Яндекс.Диск, S3) |
| 0.4 | Создать feature-ветку `migration/russia-cloud` в git |
| 0.5 | Уведомить пользователей о планируемых технических работах (email + баннер в приложении) |
| 0.6 | Задокументировать текущую версию всех зависимостей (`pip freeze > frozen-requirements.txt`) |

### Этап 1: Инфраструктура

**Продолжительность:** 1-2 дня  
**Риски:** Средние (Amvera может не поддерживать PostgREST как отдельный сервис)  
**Критерии приёмки:** Развёрнуты БД, Redis, контейнер приложения в Amvera; проверен health-check

| Шаг | Описание |
|-----|----------|
| 1.1 | Зарегистрироваться / войти в Amvera, создать проект `trudnik` |
| 1.2 | Развернуть Managed PostgreSQL (или поднять контейнер `postgres:15-alpine` с расширениями PostGIS, pgcrypto, pg_trgm) |
| 1.3 | Поднять контейнер Redis 7 (`redis:7-alpine`) через Amvera-сервисы |
| 1.4 | Поднять контейнер PostgREST (`postgrest/postgrest:v12`) с JWT-секретом |
| 1.5 | Настроить S3-бакет в Amvera для хранения файлов |
| 1.6 | Настроить сетевые правила: PostgREST доступен только из внутренней сети контейнеров |
| 1.7 | Настроить SSL-сертификат и кастомный домен (trudnik.ru или amvera.io) |
| 1.8 | Проверить связность: Flask → PostgREST → PostgreSQL; Flask → Redis; Flask → S3 |

### Этап 2: База данных

**Продолжительность:** 2-3 дня  
**Риски:** Высокие (несовместимость синтаксиса, потеря данных при миграции)  
**Критерии приёмки:** Все таблицы созданы, RLS-политики переписаны, хранимые процедуры перенесены, данные импортированы, проверена целостность

| Шаг | Описание |
|-----|----------|
| 2.1 | Применить все 48 миграций к новой БД через `psql` (после замены `auth.uid()`) |
| 2.2 | Создать таблицу `users` (локальная замена `auth.users`): id (uuid PK), email, password_hash (bcrypt), created_at, updated_at, last_login |
| 2.3 | Импортировать данные из `pg_dump` бэкапа (таблицы: profiles, jobs, applications, notifications, messages, favorites, blacklists, ratings, invitations, user_skills, job_skills, job_photos, job_favorites, push_subscriptions, email_log) |
| 2.4 | Импортировать пользователей в таблицу `users` из экспортированного `auth.users` |
| 2.5 | Проверить целостность внешних ключей (FK на user_id → profiles.id ≡ users.id) |
| 2.6 | Пересоздать индексы (GIN для полнотекстового поиска, GiST для гео-координат, B-tree для частых запросов) |
| 2.7 | Выполнить `ANALYZE` для обновления статистики |

### Этап 3: Аутентификация

**Продолжительность:** 2-3 дня  
**Риски:** Высокие (безопасность, потеря сессий пользователей)  
**Критерии приёмки:** Регистрация, вход, выход, обновление токена, смена пароля работают через локальную auth

| Шаг | Описание |
|-----|----------|
| 3.1 | Реализовать `User` модель с bcrypt-хешированием паролей |
| 3.2 | Настроить Flask-Login: `login_user()`, `logout_user()`, `@login_required` |
| 3.3 | Заменить `POST /auth/v1/token?grant_type=password` → локальная проверка email+password |
| 3.4 | Заменить `POST /auth/v1/signup` → локальное создание в `users` + `profiles` |
| 3.5 | Заменить `POST /auth/v1/token?grant_type=refresh_token` → локальная JWT-ротация |
| 3.6 | Заменить `PUT /auth/v1/user` (change password) → локальный update bcrypt-хеша |
| 3.7 | Заменить `DELETE /auth/v1/admin/users/{id}` → локальное удаление из `users` |
| 3.8 | Сгенерировать JWT-токен для PostgREST (вместо Supabase JWT) |
| 3.9 | Обновить JWT-токен в контекст-процессоре `inject_ws_config()` ([`app/__init__.py:104`](app/__init__.py:104)) |

### Этап 4: Бэкенд

**Продолжительность:** 3-4 дня  
**Риски:** Средние (большой объём изменений, регрессии)  
**Критерии приёмки:** Все blueprint'ы работают через self-hosted PostgREST, Storage работает через S3

| Шаг | Описание |
|-----|----------|
| 4.1 | Развернуть self-hosted PostgREST в Docker Compose (см. [раздел 5](#5-стратегия-замены-postgrest-api)) |
| 4.2 | Адаптировать `supabase_request()` → `postgrest_request()` (новый URL, новые заголовки) |
| 4.3 | Адаптировать `supabase_admin_request()` → `postgrest_admin_request()` (service_role → специальный JWT) |
| 4.4 | Адаптировать `supabase_rpc()` → `postgrest_rpc()` (те же RPC, новый URL) |
| 4.5 | Адаптировать `upload_to_storage()` → `upload_to_s3()` (boto3 client) |
| 4.6 | Обновить `refresh_access_token()` → локальная JWT-ротация |
| 4.7 | Обновить все blueprint'ы: заменить импорты `SUPABASE_URL`, `SUPABASE_KEY`, `SERVICE_KEY` на новые константы |
| 4.8 | Обновить `app/services/`: `job_service`, `notification_service` на новые хелперы |
| 4.9 | Обновить `app/tasks/`: `email_tasks`, `push_tasks` на `postgrest_admin_request` |

### Этап 5: Фронтенд и CSP

**Продолжительность:** 1 день  
**Риски:** Низкие  
**Критерии приёмки:** Нет CSP-блокировок, все статические ресурсы загружаются, карты работают

| Шаг | Описание |
|-----|----------|
| 5.1 | Обновить `connect-src` в CSP ([`app/__init__.py:54`](app/__init__.py:54)): заменить `https://*.supabase.co` на домен PostgREST и S3 |
| 5.2 | Проверить `img-src`: добавить домен S3-хранилища |
| 5.3 | Обновить `worker_site_url` в контекст-процессоре ([`app/__init__.py:213`](app/__init__.py:213)) |
| 5.4 | Проверить все `url_for()` в шаблонах (не должны ссылаться на Supabase) |
| 5.5 | Проверить service worker (`static/sw.js`) на предмет кэширования старых URL |
| 5.6 | Проверить генерацию URL аватаров: вместо `{SUPABASE_URL}/storage/v1/object/public/...` → S3-URL |

### Этап 6: Тестирование и верификация

**Продолжительность:** 2-3 дня  
**Риски:** Средние  
**Критерии приёмки:** Пройдены все чек-листы из [`docs/TEST_CHECKLIST.md`](docs/TEST_CHECKLIST.md)

| Шаг | Описание |
|-----|----------|
| 6.1 | Дымовое тестирование: регистрация → вход → создание задания → отклик → accept → чат → оценка |
| 6.2 | Тестирование уведомлений: Web Push + Email |
| 6.3 | Тестирование WebSocket: real-time уведомления через Redis Pub/Sub |
| 6.4 | Тестирование гео-поиска: `POST /api/jobs/nearby` (PostGIS + RLS) |
| 6.5 | Тестирование админ-панели: `/admin` |
| 6.6 | Тестирование Celery-задач: email-рассылки, push-уведомления |
| 6.7 | Нагрузочное тестирование: 50 одновременных пользователей |
| 6.8 | Тестирование PWA: офлайн-режим, установка на Android |
| 6.9 | Тестирование загрузки файлов: аватар, фото задания, документы верификации |

### Этап 7: Переключение (Cutover) и деплой

**Продолжительность:** 1 день  
**Риски:** Высокие (даунтайм, потеря данных за время переключения)  
**Критерии приёмки:** Продакшн работает на новом провайдере, пользователи могут войти и пользоваться

| Шаг | Описание |
|-----|----------|
| 7.1 | Включить режим обслуживания (maintenance mode) — баннер на сайте |
| 7.2 | Выполнить финальный инкрементальный бэкап Supabase |
| 7.3 | Импортировать инкрементальные данные в новую БД |
| 7.4 | Выполнить финальные миграции (если были изменения после этапа 2) |
| 7.5 | Закоммитить и запушить ветку `migration/russia-cloud` |
| 7.6 | Задеплоить на Amvera: `git push amvera migration/russia-cloud:master` |
| 7.7 | Проверить health-check: `GET /health` |
| 7.8 | Выполнить быстрый дымовой тест на проде |
| 7.9 | Выключить режим обслуживания |
| 7.10 | Мониторить логи и ошибки первые 24 часа |

---

## 4. Стратегия замены Supabase Auth

### 4.1. Текущая архитектура аутентификации

```
Пользователь → Flask → GoTrue API (Supabase)
                          │
                          ├── POST /auth/v1/token?grant_type=password  (login)
                          ├── POST /auth/v1/signup                     (register)
                          ├── POST /auth/v1/token?grant_type=refresh_token (refresh)
                          ├── PUT  /auth/v1/user                       (change password)
                          └── DELETE /auth/v1/admin/users/{id}         (delete account)
                          
                          ↓
                    auth.users (закрытая схема Supabase)
                    auth.refresh_tokens
```

Сессия Flask хранит:
- `session['access_token']` — JWT от Supabase
- `session['refresh_token']` — refresh_token
- `session['user_id']` — UUID пользователя
- `session['role']` — 'worker' | 'employer'

### 4.2. Предлагаемая архитектура

```
Пользователь → Flask → Локальная auth
                          │
                          ├── /login    → bcrypt.check_password() + создание JWT
                          ├── /register → INSERT INTO users + INSERT INTO profiles
                          ├── /refresh  → PyJWT refresh token rotation
                          ├── /change-password → bcrypt перехеширование
                          └── /delete-account → DELETE FROM users CASCADE
                          
                          ↓
                    public.users (новая таблица)
                    id, email, password_hash, created_at, updated_at, last_login
```

### 4.3. Миграция декоратора `@login_required`

Текущий проект использует кастомный декоратор [`@login_required`](app/decorators.py) из [`app/decorators.py`](app/decorators.py), который проверяет наличие `session['access_token']` (Supabase JWT) и вызывает `refresh_access_token()` при истечении токена.

При переходе на локальную аутентификацию есть два варианта:

**Вариант А (рекомендуемый): Интеграция Flask-Login**

Заменить кастомный декоратор на Flask-Login `@login_required`, реализовав `user_loader`:

```python
# app/__init__.py или app/decorators.py
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

class User:
    """Flask-Login User mixin для локальной auth."""
    def __init__(self, user_id, email, role):
        self.id = user_id
        self.email = email
        self.role = role

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    """Загрузить пользователя из БД по ID."""
    resp = postgrest_admin_request('GET', f'users?id=eq.{user_id}&select=id,email')
    if resp.ok and resp.json():
        u = resp.json()[0]
        # Получить роль из profiles
        role_resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=role')
        role = role_resp.json()[0]['role'] if role_resp.ok and role_resp.json() else 'worker'
        return User(u['id'], u['email'], role)
    return None
```

> **Оптимизация:** Для снижения нагрузки на PostgREST (2 HTTP-запроса при каждом запросе Flask) рекомендуется добавить in-memory кэш с TTL. Варианты:
> - `functools.lru_cache(maxsize=512)` — простой кэш без инвалидации по времени
> - `cachetools.TTLCache(maxsize=512, ttl=300)` — кэш с авто-инвалидацией через 5 минут
> - Объединить запросы через PostgREST RPC-функцию: `rpc/get_user_with_role?user_id=...`
> - Хранить `role` в таблице `users` (денормализация), чтобы избежать второго запроса

```python
```

После этого все вхождения кастомного `@login_required` в blueprint'ах заменяются на Flask-Login `@login_required`. Доступ к текущему пользователю — через `current_user.id`, `current_user.email`, `current_user.role` вместо `session['user_id']`.

**Вариант Б: Адаптация существующего декоратора**

Сохранить [`app/decorators.py`](app/decorators.py), заменив внутреннюю логику:

```python
# app/decorators.py (адаптированный)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            flash('Пожалуйста, войдите в систему.', 'warning')
            return redirect(url_for('auth.login'))
        # Проверить, не истёк ли JWT
        try:
            jwt.decode(session['access_token'], JWT_SECRET, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            if not refresh_access_token():
                session.clear()
                flash('Сессия истекла, пожалуйста, войдите снова.', 'warning')
                return redirect(url_for('auth.login'))
    return decorated_function
```

**Рекомендация:** Вариант А (Flask-Login) предпочтительнее, так как библиотека уже есть в `requirements.txt` и предоставляет成熟ую инфраструктуру: `current_user`, `login_required`, `fresh_login_required`, защиту от session fixation и т.д.

### 4.4. Новая таблица `users`

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,  -- bcrypt $2b$12$... (может быть NULL для OTP-пользователей без пароля)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login TIMESTAMPTZ
);

-- Связь с profiles (уже существует внешний ключ profiles.id → auth.users.id)
-- После миграции: profiles.id REFERENCES users(id)
```

> **Важно:** `password_hash` допускает NULL, так как в `auth.users` могут быть записи с `encrypted_password IS NULL` (пользователи, подтвердившие email через OTP, но не установившие пароль). Для таких пользователей при первом входе необходимо принудительно запросить установку пароля через `reset_password_required`.

### 4.5. Экспорт пользователей из `auth.users`

Supabase не даёт прямого доступа к `auth.users` через REST API. Варианты экспорта:

**Вариант А (рекомендуемый):** SQL Editor в Supabase Dashboard:

```sql
-- Экспорт хешей паролей
SELECT 
    id,
    email,
    encrypted_password AS password_hash,  -- Supabase использует bcrypt
    created_at,
    updated_at,
    raw_user_meta_data,
    last_sign_in_at
FROM auth.users
ORDER BY created_at;
```

**Вариант Б:** `pg_dump` схемы `auth`:

```bash
pg_dump "postgresql://postgres.xxx:password@aws-0-eu-central-1.pooler.supabase.com:6543/postgres" \
    --schema=auth \
    --table=auth.users \
    --data-only \
    --column-inserts \
    > auth_users_dump.sql
```

### 4.6. Совместимость хешей паролей

Supabase GoTrue использует **bcrypt** для хеширования паролей (тот же алгоритм, что и `bcrypt` Python-библиотека). Это означает, что хеши **полностью совместимы** — после импорта в новую таблицу `users`, пользователи смогут входить со своими старыми паролями без сброса.

```python
import bcrypt

def verify_password(password: str, password_hash: str) -> bool:
    """Проверить пароль против bcrypt-хеша."""
    return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))

def hash_password(password: str) -> str:
    """Создать bcrypt-хеш пароля."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')
```

### 4.7. Реализация JWT для PostgREST

Вместо Supabase JWT (который подписывается `supabase_key`), генерируем свой JWT, совместимый с PostgREST:

```python
import jwt
from datetime import datetime, timedelta, timezone

def generate_jwt(user_id: str, role: str) -> str:
    """Создать JWT-токен для PostgREST."""
    payload = {
        'sub': user_id,           # subject → auth.uid() в RLS
        'role': role,             # 'worker' | 'employer' | 'admin'
        'user_role': role,        # для RLS-проверок через request.jwt.claim.user_role
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def generate_refresh_token(user_id: str) -> str:
    """Создать refresh-токен (долгоживущий JWT)."""
    payload = {
        'sub': user_id,
        'type': 'refresh',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')
```

### 4.8. Адаптация `refresh_access_token()`

Текущая реализация в [`app/utils.py:278-302`](app/utils.py:278):

```python
# Было:
url = f'{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token'
resp = _requests.post(url, json={'refresh_token': refresh_token}, ...)

# Стало:
def refresh_access_token() -> bool:
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        return False
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=['HS256'])
        if payload.get('type') != 'refresh':
            return False
        user_id = payload['sub']
        # Получить роль из profiles
        role_resp = postgrest_admin_request('GET', f'profiles?id=eq.{user_id}&select=role')
        role = role_resp.json()[0]['role'] if role_resp.ok and role_resp.json() else 'worker'
        # Сгенерировать новые токены
        session['access_token'] = generate_jwt(user_id, role)
        session['refresh_token'] = generate_refresh_token(user_id)
        session.modified = True
        return True
    except Exception:
        session.clear()
        return False
```

### 4.9. Список библиотек для auth

Добавить в [`requirements.txt`](requirements.txt):

```
bcrypt>=4.2.0
```

Уже есть в requirements.txt:
- `pyjwt>=2.8.0` ✓
- `flask-login>=0.6.0` ✓ (уже установлен, но не используется для auth!)

> **Примечание:** Также потребуется `boto3` для S3-хранилища и `psycopg2-binary` для прямого подключения к БД. Полный список зависимостей см. в [секции 2.6](#26-инфраструктурные-файлы).

### 4.10. Адаптация WebSocket-аутентификации

После замены Supabase Auth на локальную, WebSocket-сервер также должен валидировать новые самостоятельно сгенерированные JWT вместо Supabase-подписанных.

**Текущая архитектура:**
- [`app/__init__.py:104`](app/__init__.py:104) — `inject_ws_config()` передаёт `access_token` клиенту для WebSocket-подключения
- WebSocket-сервер проверяет JWT при подключении (использует `SECRET_KEY` или Supabase public key)

**Изменения:**

1. **Генерация токена для WebSocket:** использовать ту же функцию `generate_jwt()`, что и для PostgREST:
   ```python
   # app/__init__.py — inject_ws_config()
   ws_config = {
       'ws_url': current_app.config['WEBSOCKET_URL'],
       'token': generate_jwt(session['user_id'], session['role']),
   }
   ```

2. **Валидация токена на WebSocket-сервере:** использовать `jwt.decode()` с `JWT_SECRET`:
   ```python
   # websocket_server/main.py
   import jwt
   
   def authenticate_websocket(token: str) -> dict | None:
       try:
           payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
           return {'user_id': payload['sub'], 'role': payload['user_role']}
       except jwt.InvalidTokenError:
           return None
   ```

3. **Обновление токена при реконнекте:** клиент должен получать свежий токен через REST API (`/api/ws-token`) и использовать его при переподключении WebSocket.

**Ключевые отличия от Supabase JWT:**
| Параметр | Supabase JWT | Новый JWT |
|----------|-------------|-----------|
| Подпись | `SUPABASE_JWT_SECRET` | `JWT_SECRET` (тот же, что для PostgREST) |
| Алгоритм | HS256 | HS256 (без изменений) |
| `sub` claim | `auth.users.id` | `users.id` |
| `role` claim | `authenticated` | `worker` \| `employer` \| `admin` |
| Доп. claims | `aud`, `iss`, `email` | `user_role` (для RLS) |

---

## 5. Стратегия замены PostgREST API

### 5.1. Вариант А: Self-hosted PostgREST (рекомендованный)

**Архитектура:**

```
Flask → HTTP → PostgREST (контейнер в Docker) → PostgreSQL
  │                   │
  │                   ├── /rest/v1/{table}    (CRUD)
  │                   ├── /rest/v1/rpc/{fn}   (хранимые процедуры)
  │                   └── Аутентификация через JWT (Authorization: Bearer)
  │
  └── POST /storage/v1/... → S3 (boto3)
```

**Почему этот вариант предпочтительнее:**

| Критерий | Self-hosted PostgREST | Прямой psycopg2 |
|----------|-----------------------|------------------|
| Совместимость с текущим кодом | **Высокая** (те же REST-эндпоинты, те же RPC, те же заголовки) | Низкая (нужно переписывать все запросы на SQL) |
| RLS-поддержка | **Полная** (PostgREST пробрасывает JWT → `request.jwt.claim.sub`) | Нет (нужно эмулировать RLS в коде) |
| Сложность миграции | **Низкая** (меняем URL и заголовки) | Высокая (пишем SQL-запросы вместо REST) |
| ORM-возможности | Встроенный (автоматическая генерация REST API из схемы БД) | Нет (нужен SQLAlchemy или сырой SQL) |
| Безопасность | RLS на уровне БД, JWT-верификация | Только на уровне приложения |
| Производительность | Высокая (один HTTP-запрос → один SQL) | Зависит от реализации |
| Обслуживание | Контейнер, авто-обновления | Только код приложения |

### 5.2. Конфигурация PostgREST

**docker-compose.yml (фрагмент):**

```yaml
postgrest:
  image: postgrest/postgrest:v12
  container_name: trudnik-postgrest
  restart: unless-stopped
  ports:
    - "3000:3000"
  environment:
    PGRST_DB_URI: ${DATABASE_URL}
    PGRST_DB_SCHEMA: public
    PGRST_DB_ANON_ROLE: anon
    PGRST_JWT_SECRET: ${JWT_SECRET}
    PGRST_DB_USE_LEGACY_GUCS: "false"
    PGRST_SERVER_PORT: "3000"
    PGRST_SERVER_HOST: "0.0.0.0"
    PGRST_LOG_LEVEL: "info"
  depends_on:
    postgres:
      condition: service_healthy
```

### 5.3. Адаптация `supabase_request()` → `postgrest_request()`

Текущий код в [`app/utils.py:309-350`](app/utils.py:309):

```python
# Было:
url = f'{SUPABASE_URL}/rest/v1/{endpoint}'
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {session.get("access_token") or SUPABASE_KEY}',
}

# Стало:
POSTGREST_URL = Config.POSTGREST_URL  # http://postgrest:3000

url = f'{POSTGREST_URL}/{endpoint}'
headers = {
    'Authorization': f'Bearer {session.get("access_token") or ANON_JWT}',
}
# Примечание: PostgREST не требует заголовка 'apikey' (это Supabase-специфичный заголовок)
# Prefer-заголовки остаются: 'Prefer': 'return=representation'
```

### 5.4. Адаптация `supabase_admin_request()` → `postgrest_admin_request()`

Текущий код в [`app/utils.py:353-421`](app/utils.py:353):

```python
# Было:
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
}

# Стало:
# Создаём специальный "админский" JWT с ролью 'admin'
# Использовать фиксированный UUID системного администратора (не nil-UUID)
SYSTEM_ADMIN_UUID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

def get_admin_jwt() -> str:
    return jwt.encode({
        'sub': SYSTEM_ADMIN_UUID,  # реальная запись в таблице users
        'role': 'admin',
        'user_role': 'admin',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(minutes=30),
    }, JWT_SECRET, algorithm='HS256')
```

> **Важно:** UUID `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` — это фиксированный идентификатор системного администратора, для которого должна быть создана реальная запись в таблице `users` на этапе 2.2. Не используйте nil-UUID (`00000000-...`), так как он может конфликтовать с проверками `user_id IS NOT NULL` в приложении.

```python

headers = {
    'Authorization': f'Bearer {get_admin_jwt()}',
}
```

### 5.5. Анонимный доступ (для неавторизованных запросов)

PostgREST использует роль `anon` для неавторизованных запросов. Нужно создать роль в БД:

```sql
CREATE ROLE anon NOLOGIN;
GRANT anon TO authenticator;
GRANT USAGE ON SCHEMA public TO anon;
GRANT SELECT ON profiles TO anon;
GRANT SELECT ON jobs TO anon;  -- только открытые через RLS
-- и т.д.
```

Анонимный JWT (короткоживущий, 7 дней; при истечении клиент запрашивает новый через `/api/anon-token`):
```python
def get_anon_jwt() -> str:
    return jwt.encode({
        'role': 'anon',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(days=7),
    }, JWT_SECRET, algorithm='HS256')
```

### 5.6. Ключевые отличия заголовков

| Заголовок | Supabase | Self-hosted PostgREST |
|-----------|----------|------------------------|
| `apikey` | Требуется (anon key или service_role key) | **Не требуется** |
| `Authorization` | `Bearer {access_token}` или `Bearer {service_role_key}` | `Bearer {JWT}` |
| `Prefer` | `return=representation` | `return=representation` (одинаково) |
| `Content-Type` | `application/json` | `application/json` (одинаково) |

---

## 6. Стратегия миграции RLS и PostgreSQL-функций

### 6.1. Замена `auth.uid()` → JWT claims

Supabase RLS использует функцию `auth.uid()`, которая извлекает `sub` из JWT, переданного через `Authorization: Bearer {jwt}`. PostgREST также пробрасывает JWT-claims в БД, но через другой механизм.

**Было (Supabase):**
```sql
CREATE POLICY "Users can update their own profile"
    ON profiles
    FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);
```

**Стало (Self-hosted PostgREST):**
```sql
CREATE POLICY "Users can update their own profile"
    ON profiles
    FOR UPDATE
    USING (current_setting('request.jwt.claim.sub')::uuid = id)
    WITH CHECK (current_setting('request.jwt.claim.sub')::uuid = id);
```

Или, если настроен `PGRST_DB_USE_LEGACY_GUCS` (до PostgREST 12):

```sql
CREATE POLICY "Users can update their own profile"
    ON profiles
    FOR UPDATE
    USING (request.jwt.claim.sub::uuid = id)
    WITH CHECK (request.jwt.claim.sub::uuid = id);
```

### 6.2. Скрипт для массовой замены в миграциях

**Важно:** В миграциях используются две формы `auth.uid()`:
- **Прямая форма:** `auth.uid()` — например, `auth.uid() = id`
- **Подзапросная форма:** `(select auth.uid())` — например, `(select auth.uid()) = id` (используется в 020_fix_performance_warnings.sql и последующих миграциях для обхода `auth_rls_initplan`)

Простая строковая замена `str.replace("auth.uid()", "...")` **сломает** подзапросную форму, превратив `(select auth.uid())` в `(select current_setting('request.jwt.claim.sub')::uuid)` — синтаксически некорректный SQL. PostgREST передаёт `sub` как GUC-переменную, и `current_setting()` уже возвращает значение — оборачивать в `(select ...)` не нужно.

Правильный подход: обрабатывать обе формы отдельными regex-паттернами:

```python
# scripts/migrate_rls_syntax.py
import re
import glob
import shutil

def migrate_rls_file(filepath: str) -> str:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Шаг 1: Замена подзапросной формы (select auth.uid()) → current_setting(...)
    # Пример: (select auth.uid()) = id → current_setting(...)::uuid = id
    content = re.sub(
        r'\(select\s+auth\.uid\(\)\)',
        "current_setting('request.jwt.claim.sub')::uuid",
        content
    )
    
    # Шаг 2: Замена прямой формы auth.uid() → current_setting(...)
    # Используем negative lookbehind/lookahead чтобы не задеть уже обработанное
    content = re.sub(
        r'(?<!\()auth\.uid\(\)(?!\))',
        "current_setting('request.jwt.claim.sub')::uuid",
        content
    )
    
    # Шаг 3: Проверка, что не осталось необработанных auth.uid()
    remaining = re.findall(r'auth\.uid\(\)', content)
    if remaining:
        print(f"  WARNING: {len(remaining)} unhandled auth.uid() occurrences remain in {filepath}")
    
    return content

for filepath in sorted(glob.glob('migrations/*.sql')):
    # Создать резервную копию перед изменением
    backup_path = filepath + '.bak'
    shutil.copy2(filepath, backup_path)
    
    new_content = migrate_rls_file(filepath)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Migrated: {filepath} (backup: {backup_path})")
```

### 6.3. Настройка JWT-секрета в PostgREST

```yaml
# docker-compose.yml
environment:
  PGRST_JWT_SECRET: ${JWT_SECRET}  # тот же секрет, что и в Flask: SECRET_KEY
```

**Важно:** `JWT_SECRET` должен быть отдельным криптографически стойким значением (минимум 32 символа), отличным от `SECRET_KEY`. Использование одного и того же значения для `SECRET_KEY` и `JWT_SECRET` снижает безопасность: компрометация одного ключа приведёт к компрометации обоих.

### 6.4. Перенос хранимых процедур

Хранимые процедуры в [`migrations/039_atomic_operations.sql`](migrations/039_atomic_operations.sql) **не требуют изменений**, так как они используют `SECURITY DEFINER` и не полагаются на `auth.uid()` внутри себя. Единственное изменение — в RLS-политиках, которые регулируют доступ к этим функциям через `supabase_rpc()`:

```sql
-- Было (если функция защищена RLS):
GRANT EXECUTE ON FUNCTION accept_application TO authenticated;

-- Стало (PostgREST):
GRANT EXECUTE ON FUNCTION accept_application TO authenticator;
```

### 6.5. Роли PostgreSQL для PostgREST

PostgREST использует многоуровневую систему ролей для аутентификации и авторизации:

**Роль `authenticator`** — точка входа для PostgREST. Все запросы проходят через неё, затем PostgREST переключается на целевую роль в зависимости от JWT claim `role`.

```sql
CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'your_db_password';  -- брать из ${DB_PASSWORD}
```

**Роль `anon`** — для неавторизованных запросов (публичный доступ к открытым ресурсам):

```sql
CREATE ROLE anon NOLOGIN;
GRANT USAGE ON SCHEMA public TO anon;
GRANT SELECT ON profiles TO anon;
GRANT SELECT ON jobs TO anon;
```

**Роли пользователей** — соответствуют значениям JWT claim `role`, генерируемого в разделе 4.6:

```sql
-- Роль для работников (worker)
CREATE ROLE worker NOLOGIN;
GRANT USAGE ON SCHEMA public TO worker;
-- Привилегии на все пользовательские таблицы
GRANT SELECT, INSERT, UPDATE, DELETE ON profiles TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON applications TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON messages TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON favorites TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON blacklists TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON user_skills TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO worker;
GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO worker;
GRANT SELECT, INSERT ON job_favorites TO worker;
GRANT SELECT ON jobs TO worker;
GRANT SELECT ON employer_details TO worker;
GRANT SELECT, INSERT, UPDATE ON ratings TO worker;
GRANT SELECT, UPDATE ON invitations TO worker;
GRANT SELECT ON hires TO worker;
GRANT SELECT ON contact_payments TO worker;

-- Роль для работодателей (employer)
CREATE ROLE employer NOLOGIN;
GRANT USAGE ON SCHEMA public TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON profiles TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON job_photos TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON job_skills TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON employer_details TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON messages TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON notifications TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO employer;
GRANT SELECT, INSERT, UPDATE, DELETE ON monetization_settings TO employer;
GRANT SELECT, INSERT, UPDATE ON applications TO employer;
GRANT SELECT, INSERT, UPDATE ON invitations TO employer;
GRANT SELECT, INSERT, UPDATE ON contact_payments TO employer;
GRANT SELECT, INSERT, UPDATE ON hires TO employer;
GRANT SELECT ON profiles TO employer;
GRANT SELECT ON user_skills TO employer;
GRANT SELECT ON ratings TO employer;
GRANT SELECT ON job_favorites TO employer;

-- Роль для администраторов (admin) — полный доступ
CREATE ROLE admin NOLOGIN;
GRANT USAGE ON SCHEMA public TO admin;
GRANT ALL ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO admin;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO admin;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO admin;

-- Делегирование всех ролей authenticator'у
GRANT anon TO authenticator;
GRANT worker TO authenticator;
GRANT employer TO authenticator;
GRANT admin TO authenticator;
```

**Примечание:** Точный список `GRANT`-привилегий должен быть уточнён на этапе реализации путём аудита фактических запросов, выполняемых каждым blueprint'ом. RLS-политики (раздел 6.1) обеспечивают дополнительную безопасность на уровне строк даже при широких табличных привилегиях.

---

## 7. Стратегия замены Storage

### 7.1. Сравнение вариантов

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| **Локальная ФС** | Простота, нет доп. затрат | Не масштабируется, потеря данных при перезапуске контейнера, бэкап сложнее |
| **S3-совместимое хранилище** | Масштабируется, CDN, бэкап, не зависит от контейнера | Дополнительная стоимость, сложнее настройка |

**Рекомендация:** S3-совместимое хранилище (Amvera S3 или Яндекс Object Storage).

### 7.2. Адаптация `upload_to_storage()`

Текущий код в [`app/utils.py:431-460`](app/utils.py:431):

```python
# Было (Supabase Storage):
url = f'{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}'
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {session["access_token"]}',
}
resp = _requests.post(url, headers=headers,
                       files={'file': (file_path, file_data, content_type)},
                       timeout=30)

# Стало (S3 через boto3):
import boto3
from botocore.config import Config as BotoConfig

_s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT,       # https://s3.amvera.io
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=BotoConfig(connect_timeout=10, read_timeout=30),
)

def upload_to_storage(bucket: str, file_path: str, file_data: bytes,
                       content_type: str) -> Optional[str]:
    try:
        _s3_client.put_object(
            Bucket=bucket,
            Key=file_path,
            Body=file_data,
            ContentType=content_type,
            ACL='public-read',  # публичный доступ для аватаров
        )
        return f'{S3_PUBLIC_URL}/{bucket}/{file_path}'
    except Exception as e:
        current_app.logger.error(f'S3 upload error: {e}')
        return None
```

### 7.3. Новые переменные окружения

```bash
# S3-хранилище
S3_ENDPOINT=https://s3.amvera.io
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_PUBLIC_URL=https://s3.amvera.io/trudnik
S3_BUCKET_AVATARS=avatars
S3_BUCKET_JOBS=job-photos
S3_BUCKET_VERIFICATION=verification-docs
```

### 7.4. Миграция существующих файлов

1. **Аудит URL в БД перед заменой.** Проверить все уникальные префиксы URL, чтобы избежать битых ссылок:
   ```sql
   -- Проверить все уникальные префиксы photo_url в profiles
   SELECT DISTINCT
       LEFT(photo_url, POSITION('/storage/' IN photo_url) + 7) AS prefix,
       COUNT(*)
   FROM profiles
   WHERE photo_url IS NOT NULL
   GROUP BY prefix;
   
   -- Аналогично для job_photos
   SELECT DISTINCT
       LEFT(photo_url, POSITION('/storage/' IN photo_url) + 7) AS prefix,
       COUNT(*)
   FROM job_photos
   WHERE photo_url IS NOT NULL
   GROUP BY prefix;
   ```
   **Критерий приёмки:** все URL должны иметь единый префикс (один Supabase-проект). Если обнаружено несколько разных префиксов — обработать каждый отдельным `UPDATE`.

2. Скачать все файлы из Supabase Storage:
   ```bash
   # Для каждого бакета:
   # avatars, job-photos, verification-docs
   for file in $(supabase storage list avatars); do
       curl -o "./exports/$file" "$SUPABASE_URL/storage/v1/object/public/avatars/$file"
   done
   ```

3. Загрузить в S3:
   ```bash
   aws s3 sync ./exports/avatars s3://avatars/ --endpoint-url $S3_ENDPOINT
   ```

4. Обновить URL в БД (использовать точный префикс, выявленный на шаге 1):
   ```sql
   UPDATE profiles
   SET photo_url = REPLACE(photo_url, 'https://xxx.supabase.co/storage/v1/object/public/', 'https://s3.amvera.io/trudnik/');
   
   UPDATE job_photos
   SET photo_url = REPLACE(photo_url, 'https://xxx.supabase.co/storage/v1/object/public/', 'https://s3.amvera.io/trudnik/');
   ```

---

## 8. Риски и план отката (Rollback)

### 8.1. Ключевые риски

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Потеря данных пользователей при экспорте `auth.users` | Средняя | Критическое | Двойной бэкап (pg_dump + SQL-экспорт), проверка количества записей |
| Несовместимость bcrypt-хешей | Низкая | Критическое | Предварительное тестирование на тестовом пользователе |
| RLS не работает с новым JWT | Средняя | Высокое | Тестирование каждой RLS-политики в staging-окружении |
| Простой сервиса при переключении | Высокая | Среднее | Maintenance mode, информирование пользователей, ночное переключение |
| PostgREST на Amvera не поддерживается | Средняя | Высокое | План «Б»: прямое подключение psycopg2 + собственный REST-слой |
| S3-хранилище Amvera недоступно | Низкая | Среднее | План «Б»: Яндекс Object Storage (совместим с boto3) |
| CSP блокирует запросы к новому домену | Средняя | Среднее | Тестирование в браузере, временный `connect-src *` для отладки |
| Celery-задачи ломаются без `SUPABASE_SERVICE_ROLE_KEY` | Средняя | Высокое | Замена на `postgrest_admin_request` с admin-JWT |
| WebSocket не пробрасывает новый JWT | Низкая | Среднее | Проверка `inject_ws_config()` в [`app/__init__.py:104`](app/__init__.py:104) |

### 8.2. Стратегия отката по этапам

| Этап | Метод отката | Время отката |
|------|-------------|--------------|
| Этап 0 | — (подготовка не затрагивает прод) | — |
| Этап 1 | Удалить ресурсы в Amvera | 30 мин |
| Этап 2 | Удалить БД в Amvera, продолжить с Supabase | 30 мин |
| Этап 3 | Откатить изменения в `auth.py` (`git revert`) | 1 час |
| Этап 4 | Откатить все изменения бэкенда (`git revert`) | 2 часа |
| Этап 5 | Откатить CSP (простая замена строки) | 15 мин |
| Этап 6 | — (тестирование на staging) | — |
| Этап 7 | **Полный откат:** переключить Render обратно на Supabase | 1 час |

### 8.3. План «Б» — оставить Supabase

Если миграция провалится на любом этапе до переключения (этап 7):

1. **Откатить код:** `git checkout main` (исходная ветка без изменений)
2. **Продолжить с Supabase:** все исходные переменные окружения остаются в Render
3. **Удалить ресурсы Amvera:** чтобы не платить за неиспользуемые ресурсы

Если миграция провалится после переключения:

1. **Экстренный откат:** изменить `WORKER_SITE_URL` обратно на Render, задеплоить `main` ветку
2. **Восстановить Supabase из бэкапа:** импортировать инкрементальные данные
3. **Уведомить пользователей:** о временной недоступности

### 8.4. Чек-лист безопасности для отката

- [ ] Бэкап Supabase хранится в 2 местах (облако + локально)
- [ ] Экспортированные `auth.users` проверены на полноту
- [ ] Код исходной (`main`) ветки проходит все тесты
- [ ] Render Dashboard доступен для ручного деплоя
- [ ] Контакты команды поддержки Supabase под рукой
- [ ] Пользователи предупреждены о возможных перебоях

### 8.5. Стратегия резервного копирования после миграции

После успешной миграции Supabase-бэкапы перестают действовать. Необходимо настроить регулярное резервное копирование на новом провайдере:

| Компонент | Метод | Расписание | Хранение |
|-----------|-------|------------|----------|
| PostgreSQL (БД) | `pg_dump -Fc` → сжатый дамп | Ежедневно, 03:00 MSK | 30 дней (S3 или локально) |
| S3-хранилище (файлы) | `aws s3 sync` → зеркалирование | Ежедневно, 04:00 MSK | 30 дней (отдельный бакет) |
| Конфигурация (env) | Копирование `.env.amvera` | При каждом изменении | Git (зашифровано) |

**Реализация через Celery Beat:**

```python
# app/tasks/backup_tasks.py
from celery import shared_task
import subprocess
import os
from datetime import datetime

@shared_task
def backup_database():
    """Ежедневный бэкап PostgreSQL."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'/data/backups/trudnik_{timestamp}.dump'
    
    cmd = [
        'pg_dump', '-Fc',
        '-d', os.environ['DATABASE_URL'],
        '-f', backup_file,
    ]
    subprocess.run(cmd, check=True)
    
    # Загрузить в S3
    import boto3
    s3 = boto3.client('s3', endpoint_url=os.environ['S3_ENDPOINT'])
    s3.upload_file(backup_file, 'backups', f'database/trudnik_{timestamp}.dump')
    
    # Удалить дампы старше 30 дней
    subprocess.run(['find', '/data/backups/', '-name', '*.dump', '-mtime', '+30', '-delete'])

@shared_task
def backup_storage():
    """Ежедневное зеркалирование S3."""
    subprocess.run([
        'aws', 's3', 'sync',
        f"s3://{os.environ['S3_BUCKET_AVATARS']}",
        f"s3://backups/avatars/",
        '--endpoint-url', os.environ['S3_ENDPOINT'],
    ])
```

**Расписание в Celery Beat:**

```python
# app/tasks/celery_app.py
from celery.schedules import crontab

beat_schedule = {
    'backup-database': {
        'task': 'app.tasks.backup_tasks.backup_database',
        'schedule': crontab(hour=3, minute=0),  # 03:00 MSK ежедневно
    },
    'backup-storage': {
        'task': 'app.tasks.backup_tasks.backup_storage',
        'schedule': crontab(hour=4, minute=0),  # 04:00 MSK ежедневно
    },
}
```

**Проверка бэкапов (еженедельно):**
- [ ] Выборочное восстановление дампа в тестовую БД
- [ ] Проверка целостности S3-бакета: `aws s3 ls s3://backups/ --recursive --summarize`
- [ ] Мониторинг свободного места: `df -h /data/backups`

---

## 9. Оценка трудозатрат

### 9.1. Детальная оценка по этапам

| Этап | Человеко-часы | Исполнители | Комментарий |
|------|---------------|-------------|-------------|
| **0. Подготовка** | **4 ч** | Backend | Экспорт, бэкап, ветка |
| 0.1 Бэкап Supabase | 1 ч | Backend | pg_dump + SQL-экспорт auth.users |
| 0.2 Сохранение бэкапа | 0.5 ч | Backend | Загрузка в облако |
| 0.3 Создание ветки | 0.5 ч | Backend | Git + CI/CD |
| 0.4 Уведомление пользователей | 1 ч | Backend | Email-рассылка + баннер |
| 0.5 Заморозка зависимостей | 1 ч | Backend | pip freeze |
| **1. Инфраструктура** | **8 ч** | DevOps | Разворачивание всех сервисов |
| 1.1 Регистрация в Amvera | 1 ч | DevOps | Создание проекта |
| 1.2 Разворачивание БД | 2 ч | DevOps | PostgreSQL + расширения |
| 1.3 Разворачивание Redis | 1 ч | DevOps | Контейнер или managed |
| 1.4 Разворачивание PostgREST | 2 ч | DevOps | Конфигурация JWT |
| 1.5 Настройка S3 | 1 ч | DevOps | Бакеты + ключи доступа |
| 1.6 Проверка связности | 1 ч | DevOps | Health-check |
| **2. База данных** | **16 ч** | Backend + DevOps | Миграция схемы и данных |
| 2.1 Применение миграций | 4 ч | Backend | 48 SQL-файлов с заменой auth.uid() |
| 2.2 Создание таблицы users | 1 ч | Backend | SQL-схема |
| 2.3 Импорт данных | 4 ч | Backend | pg_restore, валидация FK |
| 2.4 Импорт пользователей | 3 ч | Backend | auth.users → public.users |
| 2.5 Проверка целостности | 2 ч | Backend | FK, индексы, constraints |
| 2.6 Пересоздание индексов | 1 ч | Backend | GIN, GiST, B-tree |
| 2.7 ANALYZE | 1 ч | Backend | Обновление статистики |
| **3. Аутентификация** | **16 ч** | Backend | Наиболее ответственный этап |
| 3.1 Модель User + bcrypt | 2 ч | Backend | Класс User, хеширование |
| 3.2 Flask-Login интеграция | 3 ч | Backend | login_user, logout_user, user_loader |
| 3.3 Замена login | 3 ч | Backend | Переписывание auth.login() |
| 3.4 Замена register | 3 ч | Backend | Переписывание auth.register() |
| 3.5 Замена refresh token | 2 ч | Backend | refresh_access_token() |
| 3.6 Замена change password | 1 ч | Backend | profile.change_password() |
| 3.7 Замена delete account | 1 ч | Backend | profile.delete_account() |
| 3.8 JWT для PostgREST | 1 ч | Backend | Генерация совместимых JWT |
| **4. Бэкенд** | **24 ч** | Backend | Самый объёмный этап |
| 4.1 PostgREST в docker-compose | 2 ч | DevOps | Конфигурация сервиса |
| 4.2 supabase_request → postgrest_request | 4 ч | Backend | utils.py:309 |
| 4.3 supabase_admin_request | 3 ч | Backend | utils.py:353 |
| 4.4 supabase_rpc | 2 ч | Backend | utils.py:467 |
| 4.5 upload_to_storage → upload_to_s3 | 3 ч | Backend | utils.py:431 |
| 4.6 refresh_access_token | 2 ч | Backend | utils.py:278 |
| 4.7 Обновление blueprint'ов | 6 ч | Backend | 13 blueprint'ов |
| 4.8 Обновление services | 2 ч | Backend | job_service, notification_service |
| **5. Фронтенд и CSP** | **4 ч** | Frontend | Лёгкий этап |
| 5.1 CSP connect-src | 0.5 ч | Frontend | app/__init__.py:54 |
| 5.2 CSP img-src | 0.5 ч | Frontend | app/__init__.py:53 |
| 5.3 worker_site_url | 0.5 ч | Frontend | app/__init__.py:213 |
| 5.4 Проверка шаблонов | 1.5 ч | Frontend | Все Jinja2-шаблоны |
| 5.5 Service worker | 0.5 ч | Frontend | static/sw.js |
| 5.6 URL аватаров | 0.5 ч | Frontend | Проверка генерации URL |
| **6. Тестирование** | **16 ч** | QA + Backend | Полное покрытие |
| 6.1 Дымовое тестирование | 2 ч | QA | Основные сценарии |
| 6.2 Уведомления | 2 ч | QA | Web Push + Email |
| 6.3 WebSocket | 2 ч | QA | Real-time |
| 6.4 Гео-поиск | 1 ч | QA | PostGIS |
| 6.5 Админ-панель | 2 ч | QA | /admin |
| 6.6 Celery-задачи | 2 ч | QA | Email + Push |
| 6.7 Нагрузочное тестирование | 2 ч | QA | 50 пользователей |
| 6.8 PWA | 1 ч | QA | Офлайн, установка |
| 6.9 Загрузка файлов | 2 ч | QA | Аватары, фото, документы |
| **7. Переключение** | **8 ч** | Backend + DevOps | Ответственный этап |
| 7.1 Maintenance mode | 0.5 ч | Backend | Баннер |
| 7.2 Финальный бэкап | 0.5 ч | Backend | Инкрементальный |
| 7.3 Импорт данных | 2 ч | Backend | Инкрементальные данные |
| 7.4 Финальные миграции | 1 ч | Backend | Если были изменения |
| 7.5 Деплой | 1 ч | DevOps | git push amvera |
| 7.6 Health-check | 0.5 ч | DevOps | GET /health |
| 7.7 Дымовой тест | 1 ч | QA | Быстрая проверка |
| 7.8 Мониторинг | 1.5 ч | DevOps | Логи, ошибки |

### 9.2. Итого

| Категория | Человеко-часы |
|-----------|---------------|
| Подготовка | 4 |
| Инфраструктура | 8 |
| База данных | 16 |
| Аутентификация | 16 |
| Бэкенд | 24 |
| Фронтенд и CSP | 4 |
| Тестирование | 16 |
| Переключение | 8 |
| **ИТОГО** | **96 ч** |

**Рекомендуемая команда:**
- 1 Backend-разработчик (Python/Flask) — 60 ч
- 1 DevOps-инженер — 20 ч
- 1 QA-инженер — 16 ч

---

## 10. Приложения

### 10.1. Сравнительная таблица тарифов провайдеров

#### Яндекс Облако (Managed Service for PostgreSQL + Serverless Containers)

| Ресурс | Конфигурация | Цена/мес |
|--------|-------------|----------|
| Managed PostgreSQL | 2 vCPU, 8 GB RAM, 50 GB SSD | ~2 500 ₽ |
| Serverless Containers | 1 vCPU, 2 GB RAM, 100k запросов | ~1 000 ₽ |
| Object Storage | 10 GB + 100k операций | ~150 ₽ |
| Managed Redis | 1 vCPU, 2 GB RAM | ~1 500 ₽ |
| **Итого** | | **~5 150 ₽** |

#### VK Cloud

| Ресурс | Конфигурация | Цена/мес |
|--------|-------------|----------|
| DBaaS PostgreSQL | 2 vCPU, 4 GB RAM, 50 GB SSD | ~2 200 ₽ |
| Cloud Containers | 2 vCPU, 4 GB RAM | ~1 800 ₽ |
| Cloud Storage (S3) | 10 GB | ~100 ₽ |
| In-memory DB (Redis) | 1 GB | ~800 ₽ |
| **Итого** | | **~4 900 ₽** |

#### Selectel

| Ресурс | Конфигурация | Цена/мес |
|--------|-------------|----------|
| Облачная БД | 2 vCPU, 4 GB RAM, 50 GB | ~2 500 ₽ |
| Облачные контейнеры | 2 vCPU, 4 GB RAM | ~1 500 ₽ |
| S3 Object Storage | 10 GB | ~120 ₽ |
| In-memory DB | 1 GB | ~900 ₽ |
| **Итого** | | **~5 020 ₽** |

#### SberCloud

| Ресурс | Конфигурация | Цена/мес |
|--------|-------------|----------|
| CS DBaaS | 2 vCPU, 4 GB RAM, 50 GB | ~2 800 ₽ |
| Containers | 2 vCPU, 4 GB RAM | ~2 000 ₽ |
| Object Storage | 10 GB | ~150 ₽ |
| Redis | 1 GB | ~1 000 ₽ |
| **Итого** | | **~5 950 ₽** |

#### Amvera (рекомендованный)

| Ресурс | Конфигурация | Цена/мес |
|--------|-------------|----------|
| Контейнер приложения | 1 vCPU, 2 GB RAM (тариф «Базовый») | 700 ₽ |
| PostgreSQL (свой контейнер) | Включено в тариф | 0 ₽ |
| Redis (свой контейнер) | Включено в тариф | 0 ₽ |
| S3-хранилище | 10 GB (включено) | 0 ₽ |
| PostgREST (свой контейнер) | Включено в тариф | 0 ₽ |
| SSL + домен | Включено | 0 ₽ |
| **Итого** | | **~700 ₽** |

**Примечание:** Amvera предлагает фиксированную стоимость за контейнер с включёнными ресурсами. Все дополнительные сервисы (БД, Redis, PostgREST) запускаются как контейнеры внутри того же приложения. При масштабировании цена растёт линейно.

### 10.2. Новые переменные окружения

```bash
# ═══════════════════════════════════════════════════════════
# База данных и PostgREST
# ═══════════════════════════════════════════════════════════
DATABASE_URL=postgresql://authenticator:password@postgres:5432/trudnik
POSTGREST_URL=http://postgrest:3000
JWT_SECRET=your-jwt-secret-at-least-32-chars

# ═══════════════════════════════════════════════════════════
# Flask
# ═══════════════════════════════════════════════════════════
SECRET_KEY=your-secret-key-at-least-32-chars
FLASK_ENV=production

# ═══════════════════════════════════════════════════════════
# S3-хранилище
# ═══════════════════════════════════════════════════════════
S3_ENDPOINT=https://s3.amvera.io
S3_ACCESS_KEY=your_s3_access_key
S3_SECRET_KEY=your_s3_secret_key
S3_PUBLIC_URL=https://s3.amvera.io/trudnik
S3_BUCKET_AVATARS=avatars
S3_BUCKET_JOBS=job-photos
S3_BUCKET_VERIFICATION=verification-docs

# ═══════════════════════════════════════════════════════════
# Внешние API (без изменений)
# ═══════════════════════════════════════════════════════════
YANDEX_MAPS_API_KEY=your_yandex_maps_key
DEEPSEEK_API_KEY=your_deepseek_key

# ═══════════════════════════════════════════════════════════
# Redis
# ═══════════════════════════════════════════════════════════
REDIS_URL=redis://redis:6379/0

# ═══════════════════════════════════════════════════════════
# WebSocket
# ═══════════════════════════════════════════════════════════
WEBSOCKET_PORT=8001
WEBSOCKET_URL=wss://trudnik.amvera.io/ws

# ═══════════════════════════════════════════════════════════
# SMTP (без изменений)
# ═══════════════════════════════════════════════════════════
SMTP_HOST=smtp.yandex.ru
SMTP_PORT=587
SMTP_USER=notifications@trudnik.ru
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=notifications@trudnik.ru
SMTP_FROM_NAME=Trudnik
SMTP_USE_TLS=True
SMTP_USE_SSL=False
SMTP_TIMEOUT=30
SMTP_DAILY_LIMIT=1000
SMTP_RATE_LIMIT_PAUSE=1.0

# ═══════════════════════════════════════════════════════════
# Web Push (VAPID) — без изменений
# ═══════════════════════════════════════════════════════════
VAPID_PRIVATE_KEY=your_vapid_private_key
VAPID_PUBLIC_KEY=your_vapid_public_key
VAPID_CLAIMS_EMAIL=notifications@trudnik.ru
VAPID_CLAIMS_SUBJECT=mailto:notifications@trudnik.ru

# ═══════════════════════════════════════════════════════════
# Amvera
# ═══════════════════════════════════════════════════════════
WORKER_SITE_URL=https://trudnik.amvera.io/
GIT_VERSION=1.0.0
```

### 10.3. Пример docker-compose.yml для нового провайдера

```yaml
version: '3.8'

services:
  # ═══════════════════════════════════════════════════════════
  # База данных
  # ═══════════════════════════════════════════════════════════
  postgres:
    image: postgres:15-alpine
    container_name: trudnik-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: trudnik
      POSTGRES_USER: authenticator
      POSTGRES_PASSWORD: ${DB_PASSWORD:?DB_PASSWORD must be set}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    command: |
      postgres
      -c shared_preload_libraries=pg_stat_statements
      -c wal_level=replica
      -c max_wal_senders=3
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U authenticator -d trudnik"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ═══════════════════════════════════════════════════════════
  # PostgREST (REST API для PostgreSQL)
  # ═══════════════════════════════════════════════════════════
  postgrest:
    image: postgrest/postgrest:v12
    container_name: trudnik-postgrest
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      PGRST_DB_URI: postgresql://authenticator:${DB_PASSWORD:?DB_PASSWORD must be set}@postgres:5432/trudnik
      PGRST_DB_SCHEMA: public
      PGRST_DB_ANON_ROLE: anon
      PGRST_JWT_SECRET: ${JWT_SECRET}
      PGRST_DB_USE_LEGACY_GUCS: false
      PGRST_SERVER_PORT: "3000"
      PGRST_SERVER_HOST: "0.0.0.0"
      PGRST_LOG_LEVEL: "info"
    depends_on:
      postgres:
        condition: service_healthy

  # ═══════════════════════════════════════════════════════════
  # Redis (Celery-брокер + Pub/Sub)
  # ═══════════════════════════════════════════════════════════
  redis:
    image: redis:7-alpine
    container_name: trudnik-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ═══════════════════════════════════════════════════════════
  # Flask + FastAPI приложение (ASGI через Uvicorn)
  # ═══════════════════════════════════════════════════════════
  app:
    build: .
    container_name: trudnik-app
    restart: unless-stopped
    ports:
      - "${PORT:-80}:80"
    environment:
      - DATABASE_URL=postgresql://authenticator:${DB_PASSWORD:?DB_PASSWORD must be set}@postgres:5432/trudnik
      - POSTGREST_URL=http://postgrest:3000
      - JWT_SECRET=${JWT_SECRET}
      - SECRET_KEY=${SECRET_KEY}
      - REDIS_URL=redis://redis:6379/0
      - S3_ENDPOINT=${S3_ENDPOINT}
      - S3_ACCESS_KEY=${S3_ACCESS_KEY}
      - S3_SECRET_KEY=${S3_SECRET_KEY}
      - S3_PUBLIC_URL=${S3_PUBLIC_URL}
      - S3_BUCKET_AVATARS=${S3_BUCKET_AVATARS:-avatars}
      - S3_BUCKET_JOBS=${S3_BUCKET_JOBS:-job-photos}
      - S3_BUCKET_VERIFICATION=${S3_BUCKET_VERIFICATION:-verification-docs}
      - YANDEX_MAPS_API_KEY=${YANDEX_MAPS_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - SMTP_HOST=${SMTP_HOST:-smtp.yandex.ru}
      - SMTP_PORT=${SMTP_PORT:-587}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SMTP_FROM_EMAIL=${SMTP_FROM_EMAIL:-notifications@trudnik.ru}
      - SMTP_FROM_NAME=${SMTP_FROM_NAME:-Trudnik}
      - VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
      - VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}
      - VAPID_CLAIMS_EMAIL=${VAPID_CLAIMS_EMAIL:-notifications@trudnik.ru}
      - WEBSOCKET_PORT=8001
      - WEBSOCKET_URL=${WEBSOCKET_URL:-ws://localhost:8001/ws}
      - WORKER_SITE_URL=${WORKER_SITE_URL}
      - FLASK_ENV=${FLASK_ENV:-production}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      postgrest:
        condition: service_started
    command: uvicorn asgi:application --host 0.0.0.0 --port 80 --workers 1 --timeout-keep-alive 120

  # ═══════════════════════════════════════════════════════════
  # WebSocket-сервер
  # ═══════════════════════════════════════════════════════════
  websocket:
    build: .
    container_name: trudnik-websocket
    restart: unless-stopped
    ports:
      - "${WEBSOCKET_PORT:-8001}:8001"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - JWT_SECRET=${JWT_SECRET}
      - WEBSOCKET_PORT=8001
    depends_on:
      redis:
        condition: service_healthy
    command: uvicorn websocket_server.main:app --host 0.0.0.0 --port 8001 --log-level info

  # ═══════════════════════════════════════════════════════════
  # Celery Worker
  # ═══════════════════════════════════════════════════════════
  celery_worker:
    build: .
    container_name: trudnik-celery-worker
    restart: unless-stopped
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://authenticator:${DB_PASSWORD:?DB_PASSWORD must be set}@postgres:5432/trudnik
      - POSTGREST_URL=http://postgrest:3000
      - JWT_SECRET=${JWT_SECRET}
      - SECRET_KEY=${SECRET_KEY}
      - SMTP_HOST=${SMTP_HOST:-smtp.yandex.ru}
      - SMTP_PORT=${SMTP_PORT:-587}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SMTP_FROM_EMAIL=${SMTP_FROM_EMAIL:-notifications@trudnik.ru}
      - VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
      - VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}
      - VAPID_CLAIMS_EMAIL=${VAPID_CLAIMS_EMAIL:-notifications@trudnik.ru}
    depends_on:
      redis:
        condition: service_healthy
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

  # ═══════════════════════════════════════════════════════════
  # Celery Beat (периодические задачи)
  # ═══════════════════════════════════════════════════════════
  celery_beat:
    build: .
    container_name: trudnik-celery-beat
    restart: unless-stopped
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=postgresql://authenticator:${DB_PASSWORD:?DB_PASSWORD must be set}@postgres:5432/trudnik
      - POSTGREST_URL=http://postgrest:3000
      - JWT_SECRET=${JWT_SECRET}
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      redis:
        condition: service_healthy
    command: celery -A app.tasks.celery_app beat --loglevel=info

volumes:
  postgres_data:
  redis_data:
```

### 10.4. Диаграмма архитектуры после миграции

```mermaid
flowchart TB
    subgraph Amvera["Amvera Cloud (РФ)"]
        subgraph Containers["Контейнеры Docker"]
            Flask["Flask + FastAPI\nuvicorn asgi:application\n:80"]
            WS["WebSocket Server\nuvicorn\n:8001"]
            PG["PostgREST\nv12\n:3000"]
            CeleryW["Celery Worker\ncelery -A app.tasks"]
            CeleryB["Celery Beat\ncelery -A app.tasks beat"]
        end
        
        subgraph Data["Данные"]
            PGDB["PostgreSQL 15\nPostGIS, pgcrypto, pg_trgm\n:5432"]
            RedisSrv["Redis 7\nPub/Sub + Broker\n:6379"]
            S3Store["S3-совместимое\nхранилище\navatars, job-photos, docs"]
        end
    end
    
    User["Пользователь\nБраузер / PWA"] -->|HTTPS| Flask
    User -->|WSS| WS
    Flask -->|HTTP REST| PG
    PG -->|SQL| PGDB
    Flask -->|boto3| S3Store
    Flask -->|Pub/Sub| RedisSrv
    WS -->|Pub/Sub| RedisSrv
    CeleryW -->|HTTP REST| PG
    CeleryW -->|boto3| S3Store
    CeleryB -->|Redis| RedisSrv
    
    style Amvera fill:#e1f5fe,stroke:#0288d1
    style Containers fill:#fff3e0,stroke:#f57c00
    style Data fill:#e8f5e9,stroke:#388e3c
```

### 10.5. Чек-лист готовности к переключению

- [ ] Все миграции БД применены успешно
- [ ] `auth.users` экспортированы в `public.users`
- [ ] Все пароли проверены (bcrypt-совместимость)
- [ ] Регистрация нового пользователя работает
- [ ] Вход существующего пользователя работает
- [ ] Refresh token работает (проверить через 1 час после входа)
- [ ] Смена пароля работает
- [ ] Удаление аккаунта работает (каскадное)
- [ ] Создание задания работает (+ загрузка фото)
- [ ] Поиск заданий работает (включая гео-поиск)
- [ ] Отклик на задание работает (accept/reject)
- [ ] Чат работает (отправка/получение сообщений)
- [ ] WebSocket-уведомления приходят
- [ ] Email-уведомления отправляются
- [ ] Push-уведомления отправляются
- [ ] Админ-панель работает
- [ ] CSP не блокирует запросы
- [ ] PWA устанавливается и работает офлайн
- [ ] Яндекс.Карты отображаются
- [ ] Все фото/аватары отображаются (S3)
- [ ] Health-check возвращает 200
- [ ] Нагрузочный тест пройден (50 пользователей)

---

## История изменений

| Дата | Версия | Изменения |
|------|--------|-----------|
| 2026-06-19 | 1.0 | Начальная версия плана миграции |
