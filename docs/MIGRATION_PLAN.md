# План миграции проекта «Трудник» с Supabase на Amvera

**Дата:** 21 июня 2026  
**Версия:** 2.1 — актуализированы миграции (001–056), новые RPC, выравнивание с облачной схемой Supabase  
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
| **Managed PostgreSQL** | Да (Managed Service for PostgreSQL) | Да (DBaaS) | Да (Облачные базы данных) | Да (CS DBaaS) | **Да (managed кластер, до 15 реплик, суперпользователь)** | Да (managed, от 800 ₽/мес) |
| **PostGIS** | Да | Да | Да | Да | **Да (superuser → CREATE EXTENSION)** | Да |
| **Docker-контейнеры** | Да (Serverless Containers / Managed K8s) | Да (K8s Cluster / Cloud Containers) | Да (Облачные контейнеры) | Да (SberCloud Containers) | **Да (нативная платформа)** | Только на VPS (ручная установка) |
| **S3-хранилище** | Да (Object Storage) | Да (Cloud Storage) | Да (S3 Object Storage) | Да (CS Object Storage) | **Да (встроенное S3)** | Нет (нужен Яндекс Object Storage) |
| **ЦОД в РФ** | Да (Москва, Владимир) | Да (Москва, СПб) | Да (Москва, СПб) | Да (Москва) | **Да (Москва)** | Да (Москва, СПб) |
| **152-ФЗ** | Да (аттестат ФСТЭК) | Да | Да | Да (аттестован) | В процессе | **Да (аттестован)** |
| **Managed Redis** | Да | Да | Да (in-memory DB) | Да | **Да (преднастроенный сервис Redis)** | Нет (свой контейнер на VPS) |
| **Преднастроенный PostgREST** | Нет | Нет | Нет | Нет | **Да (вкладка «Преднастроенные сервисы»)** | Нет |
| **SSL/домены** | Да (Certificate Manager) | Да | Да | Да | **Да (автоматически)** | Ручная настройка (Let's Encrypt) |
| **CI/CD** | GitLab CI, GitHub Actions | GitLab CI | Встроенный CI/CD | GitLab CI | **Push-to-deploy (git push)** | Нет (ручная настройка) |
| **Простота деплоя** | Средняя (сложная документация) | Средняя | Средняя | Средняя | **Высокая (один push)** | Низкая (ручная настройка всех сервисов) |
| **Минимальная цена/мес** | ~3 500 ₽ (БД 2 vCPU + контейнеры + S3) | ~3 000 ₽ | ~3 500 ₽ | ~4 000 ₽ | **~800 ₽ (контейнер) + ~500 ₽ (БД «Начальный») + ~500 ₽ (Redis) = ~1 800 ₽** | ~400 ₽ (VPS) + ~800 ₽ (БД) + ~150 ₽ (S3) = ~1 350 ₽ |
| **Бесплатный trial** | Да (грант 4000 ₽) | Да (30 дней) | Да (3000 ₽ бонус) | Да | Да (тестовый период) | Да (30 дней VPS) |
| **Python-экосистема** | Средняя | Средняя | Средняя | Средняя | **Отличная (специализация на Python)** | Низкая (исторически PHP-хостинг) |
| **Совместимость с существующей конфигурацией** | Низкая (требует адаптации) | Низкая | Низкая | Низкая | **Высокая (уже есть .env.amvera, WORKER_SITE_URL)** | Низкая (всё с нуля) |

### 1.3. Рекомендованный выбор: **Amvera** (приоритет №1)

**Обоснование:**

1. **Существующая интеграция.** Проект уже имеет:
   - Файл [`.env.amvera`](.env.amvera) с настроенными переменными окружения
   - `WORKER_SITE_URL=https://trudnik-hyperstls.amvera.io/` в [`app/config.py:17`](app/config.py:17) — домен уже на Amvera
   - [`Dockerfile:6-11`](Dockerfile:6) содержит Amvera-совместимые директивы (`/data` volume)
   - [`docker-compose.yml`](docker-compose.yml) — требует минимальных изменений (убрать redis/postgres/postgrest контейнеры)

2. **Цена.** ~1 800 ₽/мес за полный стек:
   - Контейнер приложения (Flask + Celery): ~800 ₽/мес («Начальный»)
   - Managed PostgreSQL кластер: ~500 ₽/мес (1 реплика, «Начальный»)
   - Преднастроенный Redis: ~500 ₽/мес (встроенный S3 — бесплатно)
   - **Важно:** тарификация PostgreSQL и Redis — отдельная от контейнеров.

3. **Простота деплоя.** Push-to-deploy — `git push amvera master` — без сложной настройки K8s, без ручного CI/CD.

4. **Python-специализация.** Amvera заточена под Python-проекты, Flask/FastAPI из коробки.

5. **🔑 Ключевое преимущество: Преднастроенный PostgREST.** Amvera предоставляет PostgREST как готовый преднастроенный сервис (вкладка «Преднастроенные сервисы» → «Утилиты для баз данных» → «PostgREST»). Это означает:
   - ❌ **Не нужно** писать Dockerfile для PostgREST
   - ❌ **Не нужно** настраивать docker-compose секцию `postgrest`
   - ❌ **Не нужно** управлять сетевыми правилами для PostgREST
   - ✅ Достаточно указать `PGRST_DB_URI`, `PGRST_DB_SCHEMA`, `PGRST_DB_ANON_ROLE`, `PGRST_JWT_SECRET` в переменных окружения сервиса

6. **🔑 Преднастроенный Redis.** Amvera предоставляет Redis как готовый сервис (вкладка «Преднастроенные сервисы» → «Базы данных» → «Redis»). Замена контейнера `redis:7-alpine` из текущего docker-compose.

7. **Managed PostgreSQL кластер.** Amvera предоставляет управляемый PostgreSQL с:
   - Суперпользователем (можно установить PostGIS, pgcrypto, pg_trgm)
   - Репликами (от 1 до 15, master — запись, реплики — чтение)
   - Внутренним DNS (`amvera-<user>-cnpg-<name>-rw`)
   - Автоматическими ежедневными бэкапами (3 хранятся)
   - Ручными бэкапами по клику (до 3)

8. **Полезные вспомогательные сервисы:**
   - **pgAdmin** (преднастроенный) — веб-интерфейс для управления PostgreSQL
   - **DBeaver** (преднастроенный) — десктопный клиент БД

**Итоговая архитектура после миграции:**

| Сервис | До миграции | После миграции |
|--------|------------|----------------|
| PostgreSQL | Supabase (внешний) | Amvera Managed PostgreSQL |
| PostgREST | Supabase (встроенный) | Amvera Преднастроенный PostgREST |
| Redis | Docker-контейнер `redis:7-alpine` | Amvera Преднастроенный Redis |
| S3-хранилище | Supabase Storage | Amvera встроенное S3 |
| Auth | Supabase GoTrue | Flask-Login + bcrypt + PyJWT |
| Flask + Celery | Docker-контейнеры (Amvera) | Docker-контейнеры (Amvera, без изменений) |

**Почему НЕ Beget:**

Beget — традиционный хостинг/VPS-провайдер, который **не подходит** для этого проекта по ключевым причинам:
- ❌ **Нет нативной поддержки Docker.** Все контейнеры пришлось бы разворачивать вручную на VPS.
- ❌ **Нет S3-хранилища.** Нужен сторонний сервис (Яндекс Object Storage, +150 ₽/мес).
- ❌ **Нет CI/CD.** Каждый деплой — ручная работа: rsync, docker-compose pull/up, перезапуск.
- ❌ **Нет managed Redis.** Пришлось бы поднимать свой контейнер на VPS.
- ❌ **PHP-ориентированный.** Python поддерживается только на VPS, без специализированных инструментов.
- ❌ **Нет преднастроенного PostgREST.** Пришлось бы настраивать контейнер вручную.
- ❌ **Реальная цена выше.** VPS (~400 ₽) + managed PostgreSQL (~800 ₽) + S3-аналог (~150 ₽) = минимум ~1 350 ₽/мес без учёта трудозатрат на ручную настройку.

Beget может рассматриваться только если критически требуется **готовая сертификация 152-ФЗ прямо сейчас** и при этом Amvera по каким-то причинам недоступна.

**Риски Amvera (обновлено):**
- Тарификация PostgreSQL и Redis — отдельная от контейнеров (общая стоимость ~1 800 ₽/мес вместо ~700 ₽ в предыдущей оценке v1.0)
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
| [`docker-compose.yml`](docker-compose.yml) | **Упрощение:** удаление сервисов `redis`, `postgrest`, `postgres` (теперь это преднастроенные сервисы Amvera). Остаются: `app`, `websocket`, `celery_worker`, `celery_beat` | **Низкая** (было Средняя) | 1-74 → ~100 |
| [`Dockerfile`](Dockerfile) | **Без изменений** (ранее планировалось добавить PostgREST binary). PostgREST — преднастроенный сервис Amvera, не требует модификации Dockerfile | **Нулевая** (было Средняя) | 0 |
| [`.env.example`](.env.example) | Полная ревизия переменных окружения | **Средняя** | 1-42 |
| [`.env.amvera`](.env.amvera) | Обновление всех значений на новые (DATABASE_URL, POSTGREST_URL, REDIS_URL, S3_*) | **Средняя** | 1-45 |

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
| `migrations/001-056` (56 файлов) | Замена `auth.uid()` → `current_setting('request.jwt.claim.sub')` или `request.jwt.claim.user_id`. Миграции 049–056 — выравнивание с облачной схемой Supabase: восстановление колонок, новые таблицы (`monetization_settings`, `receipts`, `_archive_contact_payments`), исправление типов, RPC `get_job_stats` и `nearby_jobs` | **Высокая** |

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

### 2.7. Сводка по сложности (обновлено v2.0)

| Сложность | Количество файлов | Примечание |
|-----------|-------------------|------------|
| Высокая | 3 (`utils.py`, `auth.py`, 56 migration files) | Без изменений |
| Средняя | 11 (было 14) | Dockerfile и render.yaml выпали (PostgREST — преднастроенный сервис) |
| Низкая | 15+ | docker-compose.yml понижен со Средней до Низкой (только удаление сервисов) |
| Нулевая | 4 (было 2) | Добавлены Dockerfile и render.yaml |

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

**Продолжительность:** 0.5 дня (было 1 день)
**Риски:** Низкие
**Критерии приёмки:** Полный бэкап Supabase, экспортированные данные, создан feature-ветка `migration/russia-cloud`

| Шаг | Описание |
|-----|----------|
| 0.1 | Создать полный бэкап Supabase: `pg_dump` через connection string (порт 6543 — pooler) |
| 0.2 | Экспортировать `auth.users` через Supabase Dashboard (SQL Editor) с помощью `auth.raw_user_meta_data()` |
| 0.3 | Сохранить бэкап в защищённое облачное хранилище (Яндекс.Диск, S3) |
| 0.4 | Создать feature-ветку `migration/russia-cloud` в git |
| 0.5 | Уведомить пользователей о планируемых технических работах (email + баннер в приложении) |
| 0.6 | Задокументировать текущую версию всех зависимостей (`pip freeze > frozen-requirements.txt`) |

### Этап 1: Инфраструктура (обновлено v2.0)

**Продолжительность:** 1-2 часа (было 1-2 дня)  
**Риски:** Низкие (было Средние — все сервисы создаются кнопками в админке Amvera)  
**Критерии приёмки:** Созданы Managed PostgreSQL, Преднастроенный PostgREST, Преднастроенный Redis; проверен health-check

| Шаг | Описание | Где |
|-----|----------|-----|
| 1.1 | Создать **Managed PostgreSQL** кластер: тариф «Начальный», 1 реплика, активировать Superuser Access | Админка Amvera → Базы данных → PostgreSQL → Создать |
| 1.2 | Запомнить внутренние DNS: `amvera-<user>-cnpg-<name>-rw` (запись), `-ro` (чтение) | Страница «Инфо» кластера |
| 1.3 | Установить расширения через суперпользователя: `CREATE EXTENSION postgis; CREATE EXTENSION pgcrypto; CREATE EXTENSION pg_trgm;` | DBeaver/pgAdmin → подключение к кластеру |
| 1.4 | Создать **Преднастроенный PostgREST**: указать `PGRST_DB_URI`, `PGRST_DB_SCHEMA=public`, `PGRST_DB_ANON_ROLE=web_anon`, `PGRST_JWT_SECRET` | Админка Amvera → Преднастроенные сервисы → Утилиты для БД → PostgREST |
| 1.5 | Запомнить внутренний DNS PostgREST (для `POSTGREST_URL`) | Страница «Инфо» сервиса PostgREST |
| 1.6 | Создать **Преднастроенный Redis**: тариф «Начальный» | Админка Amvera → Преднастроенные сервисы → Базы данных → Redis |
| 1.7 | Запомнить внутренний DNS Redis (для `REDIS_URL`) | Страница «Инфо» сервиса Redis |
| 1.8 | Настроить S3-бакет в Amvera для хранения файлов | Админка Amvera → Хранилище |
| 1.9 | Проверить связность: Flask → PostgREST → PostgreSQL; Flask → Redis; Flask → S3 | Health-check эндпоинт |

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

## 5. Стратегия замены Supabase REST API (PostgREST как преднастроенный сервис Amvera)

### 5.1. Архитектура: Преднастроенный PostgREST (новое в v2.0)

Amvera предоставляет PostgREST как **преднастроенный сервис** (вкладка «Преднастроенные сервисы» → «Утилиты для баз данных» → «PostgREST»). Это устраняет необходимость в ручном разворачивании контейнера `postgrest/postgrest:v12`.

**Архитектура:**

```
Flask (контейнер) → HTTP → Преднастроенный PostgREST (Amvera) → Managed PostgreSQL (Amvera)
   │                                │
   │                                ├── /{table}              (CRUD)
   │                                ├── /rpc/{fn}             (хранимые процедуры)
   │                                └── JWT (Authorization: Bearer)
   │
   └── boto3 → Встроенное S3 (Amvera)
```

**Что даёт преднастроенный PostgREST:**

| Задача | Было (v1.0) | Стало (v2.0) |
|--------|-------------|--------------|
| Разворачивание | Контейнер `postgrest/postgrest:v12` в docker-compose | Кнопка «Создать преднастроенный сервис» в админке Amvera |
| Конфигурация | `docker-compose.yml` секция postgrest | 4 переменные окружения в админке Amvera |
| Сетевая изоляция | `expose: "3000"` в docker-compose | Автоматически: внутренний DNS Amvera |
| SSL/TLS | Ручная настройка | Автоматически: Amvera управляет сертификатами |
| Health-check | Docker healthcheck | Автоматически: Amvera мониторит сервис |
| Обновления | Ручной `docker pull` | Автоматически: Amvera обновляет образ |
| Масштабирование | Ручное | Выбор тарифа в админке |

### 5.2. Конфигурация Преднастроенного PostgREST

Переменные окружения, которые нужно задать в админке Amvera при создании сервиса:

| Переменная | Значение | Описание |
|-----------|----------|----------|
| `PGRST_DB_URI` | `postgresql://user:pass@amvera-<user>-cnpg-<project>-rw:5432/<db>` | Строка подключения к Managed PostgreSQL (внутренний DNS) |
| `PGRST_DB_SCHEMA` | `public` | Схема БД |
| `PGRST_DB_ANON_ROLE` | `web_anon` | Роль для неаутентифицированных запросов |
| `PGRST_JWT_SECRET` | `{{JWT_SECRET}}` | Секрет для верификации JWT (должен совпадать с Flask) |
| `PGRST_SERVER_PORT` | `3000` | Порт (по умолчанию) |

**Примечание:** Заголовок `apikey` (Supabase-специфичный) не требуется. PostgREST проверяет только `Authorization: Bearer {JWT}`.

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
POSTGREST_URL = Config.POSTGREST_URL  # http://amvera-<user>-<project>-postgrest:3000

url = f'{POSTGREST_URL}/{endpoint}'
headers = {
    'Authorization': f'Bearer {session.get("access_token") or ANON_JWT}',
}
```

### 5.4. Адаптация `supabase_admin_request()` → `postgrest_admin_request()`

```python
# Было:
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
}

# Стало:
# Админский JWT с ролью 'admin', фиксированный UUID системного администратора
SYSTEM_ADMIN_UUID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'

def get_admin_jwt() -> str:
    return jwt.encode({
        'sub': SYSTEM_ADMIN_UUID,
        'role': 'admin',
        'user_role': 'admin',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(minutes=30),
    }, JWT_SECRET, algorithm='HS256')

headers = {
    'Authorization': f'Bearer {get_admin_jwt()}',
}
```

### 5.5. Анонимный доступ

```python
def get_anon_jwt() -> str:
    return jwt.encode({
        'role': 'anon',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(days=7),
    }, JWT_SECRET, algorithm='HS256')
```

### 5.6. Ключевые отличия заголовков

| Заголовок | Supabase | Преднастроенный PostgREST Amvera |
|-----------|----------|----------------------------------|
| `apikey` | Требуется | **Не требуется** |
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

Хранимые процедуры в [`migrations/039_atomic_operations.sql`](migrations/039_atomic_operations.sql), [`migrations/048_atomic_apply_job.sql`](migrations/048_atomic_apply_job.sql), [`migrations/052_add_job_stats_rpc.sql`](migrations/052_add_job_stats_rpc.sql) и [`migrations/056_add_nearby_jobs_rpc.sql`](migrations/056_add_nearby_jobs_rpc.sql) **не требуют изменений**, так как они используют `SECURITY DEFINER` и не полагаются на `auth.uid()` внутри себя. Единственное изменение — в RLS-политиках, которые регулируют доступ к этим функциям через `supabase_rpc()`:

Полный список RPC-функций после миграций 001–056:
- `accept_application` / `reject_application` — принятие/отклонение отклика
- `apply_job_atomic` — атомарный отклик на задание
- `delete_job_cascade` — каскадное удаление задания
- `delete_user_cascade` — каскадное удаление пользователя
- `get_job_stats` — статистика публикаций (админ-панель)
- `nearby_jobs` — геопоиск ближайших заданий (PostGIS)

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
| PostgREST на Amvera не поддерживается | ~~Средняя~~ **Низкая (v2.0)** | ~~Высокое~~ **Низкое** | **Снят:** PostgREST — официальный преднастроенный сервис Amvera (вкладка «Преднастроенные сервисы» → «PostgREST»). План «Б» не требуется |
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

### 9.1. Детальная оценка по этапам (обновлено v2.0)

| Этап | Человеко-часы | Было (v1.0) | Исполнители | Комментарий |
|------|---------------|-------------|-------------|-------------|
| **0. Подготовка** | **2 ч** | 4 ч | Backend | Экспорт, бэкап, ветка |
| 0.1 Бэкап Supabase | 1 ч | 1 ч | Backend | pg_dump + SQL-экспорт auth.users |
| 0.2 Сохранение бэкапа | 0.5 ч | 0.5 ч | Backend | Загрузка в облако |
| 0.3 Создание ветки | 0.5 ч | 0.5 ч | Backend | Git |
| **1. Инфраструктура** | **2 ч** | ~~8 ч~~ | DevOps | **−6 ч:** PostgREST и Redis создаются кнопками |
| 1.1 Создание Managed PostgreSQL | 0.5 ч | 2 ч | DevOps | Кнопка «Создать БД» в админке |
| 1.2 Создание Преднастроенного PostgREST | 0.5 ч | — | DevOps | Кнопка «Создать преднастроенный сервис» |
| 1.3 Создание Преднастроенного Redis | 0.25 ч | 1 ч | DevOps | Кнопка «Создать преднастроенный сервис» |
| 1.4 Установка расширений БД | 0.25 ч | — | Backend | `CREATE EXTENSION postgis/pgcrypto/pg_trgm` |
| 1.5 Настройка S3 | 0.25 ч | 1 ч | DevOps | Бакеты + ключи |
| 1.6 Проверка связности | 0.25 ч | 1 ч | DevOps | Health-check |
| **2. База данных** | **16 ч** | 16 ч | Backend + DevOps | Без изменений |
| **3. Аутентификация** | **16 ч** | 16 ч | Backend | Без изменений |
| **4. Бэкенд** | **18 ч** | ~~24 ч~~ | Backend | **−6 ч:** убрана настройка PostgREST в docker-compose |
| 4.1 ~~PostgREST в docker-compose~~ | ~~0 ч~~ | ~~2 ч~~ | — | **Исключено:** PostgREST — преднастроенный сервис |
| 4.2 supabase_request → postgrest_request | 4 ч | 4 ч | Backend | utils.py |
| 4.3 supabase_admin_request | 3 ч | 3 ч | Backend | utils.py |
| 4.4 supabase_rpc | 2 ч | 2 ч | Backend | utils.py |
| 4.5 upload_to_storage → upload_to_s3 | 3 ч | 3 ч | Backend | utils.py |
| 4.6 refresh_access_token | 2 ч | 2 ч | Backend | utils.py |
| 4.7 Обновление blueprint'ов | 4 ч | 6 ч | Backend | 13 blueprint'ов (упрощённые заголовки) |
| 4.8 Обновление services | 2 ч | 2 ч | Backend | job_service, notification_service |
| **5. Фронтенд и CSP** | **4 ч** | 4 ч | Frontend | Без изменений |
| **6. Тестирование** | **16 ч** | 16 ч | QA + Backend | Без изменений |
| **7. Переключение** | **8 ч** | 8 ч | Backend + DevOps | Без изменений |

### 9.2. Итого

| Категория | v1.0 (ч) | v2.0 (ч) | Экономия |
|-----------|----------|----------|----------|
| Подготовка | 4 | 2 | −2 ч |
| Инфраструктура | 8 | **2** | **−6 ч** |
| База данных | 16 | 16 | — |
| Аутентификация | 16 | 16 | — |
| Бэкенд | 24 | **18** | **−6 ч** |
| Фронтенд и CSP | 4 | 4 | — |
| Тестирование | 16 | 16 | — |
| Переключение | 8 | 8 | — |
| **ИТОГО** | **96 ч** | **82 ч** | **−14 ч (−15%)** |

**Рекомендуемая команда:**
- 1 Backend-разработчик (Python/Flask) — 52 ч
- 1 DevOps-инженер — 14 ч (было 20 ч)
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

#### Amvera (рекомендованный) — обновлено v2.0

| Ресурс | Конфигурация | Цена/мес |
|--------|-------------|----------|
| Контейнер приложения (Flask + Celery Worker + Celery Beat + WebSocket) | 1 vCPU, 2 GB RAM (тариф «Начальный») | ~800 ₽ |
| **Managed PostgreSQL** | 1 реплика, тариф «Начальный» (суперпользователь, бэкапы, PostGIS/pgcrypto/pg_trgm) | ~500 ₽ |
| **Преднастроенный PostgREST** | Включено в тариф контейнера | 0 ₽ |
| **Преднастроенный Redis** | Тариф «Начальный» | ~500 ₽ |
| Встроенное S3-хранилище | 10 GB (включено) | 0 ₽ |
| SSL + домен | Включено | 0 ₽ |
| **Итого** | | **~1 800 ₽** |

**Примечание (v2.0):** В отличие от оценки v1.0 (~700 ₽), актуальная стоимость учитывает, что Managed PostgreSQL и Преднастроенный Redis тарифицируются отдельно от контейнера приложения. Однако все три сервиса (PostgreSQL, PostgREST, Redis) создаются кнопками в админке, без необходимости писать Dockerfile или docker-compose секции.

### 10.2. Новые переменные окружения (обновлено v2.0)

```bash
# ═══════════════════════════════════════════════════════════
# База данных и PostgREST (Amvera внутренние DNS)
# ═══════════════════════════════════════════════════════════
DATABASE_URL=postgresql://user:password@amvera-<user>-cnpg-<project>-rw:5432/<dbname>
POSTGREST_URL=http://amvera-<user>-<project>-postgrest:3000
JWT_SECRET=your-jwt-secret-at-least-32-chars

# ═══════════════════════════════════════════════════════════
# Flask
# ═══════════════════════════════════════════════════════════
SECRET_KEY=your-secret-key-at-least-32-chars
FLASK_ENV=production

# ═══════════════════════════════════════════════════════════
# Redis (Amvera Преднастроенный Redis, внутренний DNS)
# ═══════════════════════════════════════════════════════════
REDIS_URL=redis://amvera-<user>-<project>-redis:6379/0

# ═══════════════════════════════════════════════════════════
# S3-хранилище (встроенное Amvera)
# ═══════════════════════════════════════════════════════════
S3_ENDPOINT=https://s3.amvera.io
S3_ACCESS_KEY=your_s3_access_key
S3_SECRET_KEY=your_s3_secret_key
S3_PUBLIC_URL=https://s3.amvera.io/trudnik
S3_BUCKET_AVATARS=avatars
S3_BUCKET_JOBS=job-photos
S3_BUCKET_VERIFICATION=verification-docs

# ═══════════════════════════════════════════════════════════
# WebSocket
# ═══════════════════════════════════════════════════════════
WEBSOCKET_PORT=8001
WEBSOCKET_URL=wss://trudnik.amvera.io/ws

# ═══════════════════════════════════════════════════════════
# Amvera
# ═══════════════════════════════════════════════════════════
WORKER_SITE_URL=https://trudnik.amvera.io/
GIT_VERSION=2.0.0
```

> **Примечание (v2.0):** `POSTGREST_URL`, `REDIS_URL` и `DATABASE_URL` используют внутренние DNS-имена Amvera (вида `amvera-<user>-<service>-<project>`). Точные имена доступны на странице «Инфо» каждого сервиса. Внешние API (Yandex Maps, SMTP, VAPID) остаются без изменений.

### 10.3. Пример docker-compose.yml для Amvera (обновлено v2.0)

> **Важно:** PostgREST, Redis и PostgreSQL — преднастроенные сервисы Amvera, создаются через админку. В docker-compose остаются только контейнеры приложения.

```yaml
version: '3.8'

services:
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
      - DATABASE_URL=${DATABASE_URL}
      - POSTGREST_URL=${POSTGREST_URL}
      - JWT_SECRET=${JWT_SECRET}
      - SECRET_KEY=${SECRET_KEY}
      - REDIS_URL=${REDIS_URL}
      - S3_ENDPOINT=${S3_ENDPOINT}
      - S3_ACCESS_KEY=${S3_ACCESS_KEY}
      - S3_SECRET_KEY=${S3_SECRET_KEY}
      - S3_PUBLIC_URL=${S3_PUBLIC_URL}
      - S3_BUCKET_AVATARS=${S3_BUCKET_AVATARS:-avatars}
      - S3_BUCKET_JOBS=${S3_BUCKET_JOBS:-job-photos}
      - S3_BUCKET_VERIFICATION=${S3_BUCKET_VERIFICATION:-verification-docs}
      - YANDEX_MAPS_API_KEY=${YANDEX_MAPS_API_KEY}
      - SMTP_HOST=${SMTP_HOST:-smtp.yandex.ru}
      - SMTP_PORT=${SMTP_PORT:-587}
      - SMTP_USER=${SMTP_USER}
      - SMTP_PASSWORD=${SMTP_PASSWORD}
      - SMTP_FROM_EMAIL=${SMTP_FROM_EMAIL:-notifications@trudnik.ru}
      - VAPID_PRIVATE_KEY=${VAPID_PRIVATE_KEY}
      - VAPID_PUBLIC_KEY=${VAPID_PUBLIC_KEY}
      - VAPID_CLAIMS_EMAIL=${VAPID_CLAIMS_EMAIL:-notifications@trudnik.ru}
      - WEBSOCKET_PORT=8001
      - WEBSOCKET_URL=${WEBSOCKET_URL:-ws://localhost:8001/ws}
      - WORKER_SITE_URL=${WORKER_SITE_URL}
      - FLASK_ENV=${FLASK_ENV:-production}
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
      - REDIS_URL=${REDIS_URL}
      - JWT_SECRET=${JWT_SECRET}
      - WEBSOCKET_PORT=8001
    command: uvicorn websocket_server.main:app --host 0.0.0.0 --port 8001 --log-level info

  # ═══════════════════════════════════════════════════════════
  # Celery Worker
  # ═══════════════════════════════════════════════════════════
  celery_worker:
    build: .
    container_name: trudnik-celery-worker
    restart: unless-stopped
    environment:
      - REDIS_URL=${REDIS_URL}
      - DATABASE_URL=${DATABASE_URL}
      - POSTGREST_URL=${POSTGREST_URL}
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
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4

  # ═══════════════════════════════════════════════════════════
  # Celery Beat (периодические задачи)
  # ═══════════════════════════════════════════════════════════
  celery_beat:
    build: .
    container_name: trudnik-celery-beat
    restart: unless-stopped
    environment:
      - REDIS_URL=${REDIS_URL}
      - DATABASE_URL=${DATABASE_URL}
      - POSTGREST_URL=${POSTGREST_URL}
      - JWT_SECRET=${JWT_SECRET}
      - SECRET_KEY=${SECRET_KEY}
    command: celery -A app.tasks.celery_app beat --loglevel=info

# Примечание (v2.0):
# - postgres — удалён (Amvera Managed PostgreSQL)
# - postgrest — удалён (Amvera Преднастроенный PostgREST)
# - redis — удалён (Amvera Преднастроенный Redis)
# - volumes — удалены (управляются Amvera)
# - depends_on — удалены (сервисы Amvera доступны через внутренний DNS всегда)
```

**Сравнение docker-compose до и после:**

| Сервис | Было (v1.0) | Стало (v2.0) |
|--------|------------|-------------|
| `postgres` | Контейнер `postgres:15-alpine` | ❌ Удалён (Amvera Managed PostgreSQL) |
| `postgrest` | Контейнер `postgrest/postgrest:v12` | ❌ Удалён (Amvera Преднастроенный PostgREST) |
| `redis` | Контейнер `redis:7-alpine` | ❌ Удалён (Amvera Преднастроенный Redis) |
| `app` | Flask + FastAPI | ✅ Остался |
| `websocket` | WebSocket Server | ✅ Остался |
| `celery_worker` | Celery Worker | ✅ Остался |
| `celery_beat` | Celery Beat | ✅ Остался |
| `volumes` | postgres_data, redis_data | ❌ Удалены (управляются Amvera) |
| **Итого контейнеров** | **7** | **4** |

### 10.4. Диаграмма архитектуры после миграции (обновлено v2.0)

```mermaid
flowchart TB
    subgraph Amvera["Amvera Cloud (Москва, РФ)"]
        subgraph Containers["Docker-контейнеры (4 шт.)"]
            Flask["Flask + FastAPI\nuvicorn asgi:application\n:80"]
            WS["WebSocket Server\nuvicorn\n:8001"]
            CeleryW["Celery Worker\ncelery -A app.tasks"]
            CeleryB["Celery Beat\ncelery -A app.tasks beat"]
        end
        
        subgraph Preconf["Преднастроенные сервисы"]
            PG["PostgREST\n(преднастроенный)\n:3000"]
        end
        
        subgraph Data["Данные"]
            PGDB["Managed PostgreSQL\nPostGIS, pgcrypto, pg_trgm\nавто-бэкапы, репликация"]
            RedisSrv["Преднастроенный Redis\nPub/Sub + брокер Celery"]
            S3Store["Встроенное S3\navatars, job-photos, docs"]
        end
    end
    
    User["Пользователь\nБраузер / PWA"] -->|HTTPS| Flask
    User -->|WSS| WS
    Flask -->|HTTP REST + JWT| PG
    PG -->|SQL| PGDB
    Flask -->|boto3| S3Store
    Flask -->|Pub/Sub| RedisSrv
    WS -->|Pub/Sub| RedisSrv
    CeleryW -->|HTTP REST + JWT| PG
    CeleryW -->|boto3| S3Store
    CeleryB -->|Redis| RedisSrv
    
    style Amvera fill:#e1f5fe,stroke:#0288d1
    style Containers fill:#fff3e0,stroke:#f57c00
    style Preconf fill:#f3e5f5,stroke:#7b1fa2
    style Data fill:#e8f5e9,stroke:#388e3c
```

> **Легенда (v2.0):**
> - 🟠 **Контейнеры** — 4 Docker-контейнера, управляемые через docker-compose
> - 🟣 **Преднастроенные сервисы** — 1 сервис (PostgREST), созданный кнопкой в админке Amvera
> - 🟢 **Данные** — 3 сервиса (Managed PostgreSQL, Преднастроенный Redis, S3), созданные через админку Amvera

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
| 2026-06-21 | 2.1 | **Актуализация миграций:** количество миграций 001–056 (было 001–048). Миграции 049–056 — выравнивание с облачной схемой Supabase: восстановление колонок `jobs`, новые таблицы (`monetization_settings`, `receipts`, `_archive_contact_payments`), исправление типов (varchar→text, numeric→float8), RPC `get_job_stats` и `nearby_jobs`. Обновлён список RPC-функций |
| 2026-06-20 | 2.0 | **Актуализация под преднастроенные сервисы Amvera:** PostgREST и Redis — готовые сервисы (создаются кнопками в админке). Managed PostgreSQL — отдельный тариф с суперпользователем. docker-compose упрощён с 7 до 4 контейнеров. Оценка трудозатрат снижена на 14 ч (−15%). Цена скорректирована: ~1 800 ₽/мес вместо ~700 ₽. Удалены риски «PostgREST не поддерживается» и «нужен свой контейнер Redis» |
| 2026-06-19 | 1.0 | Начальная версия плана миграции |
