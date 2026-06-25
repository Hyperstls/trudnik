# Итоговый отчёт комплексного код-ревью проекта «Трудник»

**Дата:** 2026-06-22
**Охвачено:** ~131 файл, ~300K строк кода
**Этапов:** 8 (0-7)

---

## 1. Общая статистика

| Этап | Область | Файлов | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|------|---------|--------|----------|------|--------|-----|-------|
| 1 | Инфраструктура | 15 | 2 | 13 | 31 | 17 | 63 |
| 2A | Blueprints A (auth, jobs, jobs_api) | 3 | 0 | 4 | 13 | 13 | 30 |
| 2B | Blueprints B (admin, applications) | 2 | 1 | 6 | 14 | 9 | 30 |
| 2C | Blueprints C (profile, chat, notifications, ratings, employers, favorites, blacklist, seo) | 8 | 0 | 3 | 11 | 27 | 41 |
| 3 | Сервисы | 5 | 0 | 16 | 18 | 9 | 43 |
| 4-5 | Celery + Utils | 5 | 1 | 8 | 20 | 14 | 43 |
| 6 | Фронтенд | 16 | 0 | 1 | 12 | 29 | 42 |
| 7 | Скрипты/Миграции | 77 | 1 | 3 | 15 | 37 | 56 |
| **ИТОГО** | | **~131** | **5** | **54** | **134** | **155** | **348** |

---

## 2. Ключевые cross-cutting проблемы

### 2.1 Неатомарные операции (check-then-act без транзакций)

**Приоритет: CRITICAL/HIGH**

Наиболее массовая и опасная категория проблем. Множественные последовательные HTTP-запросы к PostgREST без транзакционной защиты:

| # | Файл:Строка | Операция | Проблема | Есть RPC? |
|---|-------------|----------|----------|-----------|
| 1 | [`jobs.py:553-565`](app/blueprints/jobs.py) | `cancel_job()` | Проверка accepted-откликов (GET) и отмена (PATCH) — race condition | НЕТ |
| 2 | [`jobs.py:663-668`](app/blueprints/jobs.py) | `force-complete` | Массовый reject pending + установка completed — две неатомарные операции | НЕТ |
| 3 | [`jobs.py:774-823`](app/blueprints/jobs.py) | `edit_job()` | Проверка `has_accepted` и последующее PATCH — race condition | НЕТ |
| 4 | [`jobs_api.py:206-223`](app/blueprints/jobs_api.py) | `respond_invitation()` accept | POST application + PATCH jobs `current_workers` — неатомарны | НЕТ |
| 5 | [`jobs_api.py:122-138`](app/blueprints/jobs_api.py) | `invite_worker()` | Проверка свободных мест и создание приглашения — неатомарны | НЕТ |
| 6 | [`auth.py:177-227`](app/blueprints/auth.py) | `register()` | RPC register_user → PATCH profile → цикл POST user_skills. При сбое — полу-созданный пользователь | НЕТ |
| 7 | [`applications.py:280-362`](app/blueprints/applications.py) | `api_withdraw_application()` | 6 HTTP-запросов без транзакции: GET→GET→PATCH→NOTIFY→PATCH→DELETE | НЕТ |
| 8 | [`applications.py:571-637`](app/blueprints/applications.py) | `cancel_application()` | 5 запросов: GET→GET→GET→PATCH→PATCH. Двойная отмена → `current_workers` в минус | НЕТ |
| 9 | [`applications.py:437-441`](app/blueprints/applications.py) | accept rejected | PATCH rejected→pending вне RPC `accept_application`. При сбое — потеря данных | НЕТ |
| 10 | [`applications.py:187-243`](app/blueprints/applications.py) | `apply_selected()` | Массовая подача заявок обходит RPC `apply_job_atomic` — не проверяются blacklist, слоты | НЕТ |
| 11 | [`admin.py:300-308`](app/blueprints/admin.py) | `delete_skill()` | Три неатомарных DELETE: user_skills → job_skills → skills. При сбое — навык-сирота | НЕТ |
| 12 | [`ratings.py:190`](app/blueprints/ratings.py) → [`utils.py:1287-1295`](app/utils.py) | `upsert_rating()` | Оценка сохранена, но `profiles.rating` может быть устаревшим. Внутри `update_rating` — GET+PATCH (ещё одна неатомарная пара) | НЕТ |
| 13 | [`ratings.py:148-180`](app/blueprints/ratings.py) | `upsert_rating()` | Проверка существования (GET) + INSERT с retry-логикой — до 3 HTTP-запросов на одну операцию | НЕТ |
| 14 | [`employers.py:153-166`](app/blueprints/employers.py) | `toggle_favorite()` | GET проверка + DELETE/POST — race condition | НЕТ |
| 15 | [`admin.py:103,141`](app/blueprints/admin.py) | `update_user_role/update_job_status` | Не проверяется `resp.ok` — всегда flash success | НЕТ |

**Существующие RPC (8):**
- `accept_application` (039) — атомарный accept + инкремент `current_workers`
- `reject_application` (039) — атомарный reject
- `apply_job_atomic` (048) — атомарный отклик с проверками
- `delete_job_cascade` (039) — каскадное удаление
- `delete_user_cascade` (039) — каскадное удаление
- `get_job_stats` (052) — статистика (read-only)
- `nearby_jobs` (056) — геопоиск (read-only)
- `exec_sql` — выполнение SQL (admin)

**Недостающие RPC (требуется создать):**
1. `withdraw_application_atomic` — атомарный отзыв заявки с декрементом `current_workers`
2. `cancel_worker_atomic` — атомарная отмена с проверкой статуса и декрементом
3. `force_complete_job` — атомарный reject всех pending + установка completed
4. `cancel_job_atomic` — атомарная отмена задания с проверкой accepted-откликов
5. `accept_invitation_atomic` — атомарное принятие приглашения: создание заявки + инкремент
6. `register_user_full` — атомарная регистрация: пользователь + профиль + навыки
7. `delete_skill_cascade` — атомарное удаление навыка: user_skills → job_skills → skills
8. `upsert_rating_atomic` — атомарный UPSERT оценки + пересчёт `profiles.rating`
9. `toggle_favorite_atomic` — атомарное переключение избранного
10. `search_jobs_page` — пагинированный поиск с фильтрацией на стороне БД

---

### 2.2 Сломанная пагинация (фильтрация после limit/offset)

**Приоритет: HIGH**

Фильтрация в Python применяется ПОСЛЕ того, как из БД уже получена страница с limit/offset. Результат: страницы неравномерны (0-20 записей вместо 20), часть данных пропускается.

| # | Файл:Строка | Эндпоинт | Что фильтруется в Python |
|---|-------------|----------|--------------------------|
| 1 | [`jobs.py:126-185`](app/blueprints/jobs.py) | `index()` — главная лента | Статус, expires_at, blacklist, навыки, радиус, детальное описание |
| 2 | [`employers.py:46-51`](app/blueprints/employers.py) | `employers_list()` | Чёрный список |
| 3 | [`employers.py:77-78`](app/blueprints/employers.py) | `employers_list()` | `total_pages` вычислен от уже отфильтрованного (неверно) |
| 4 | [`job_service.py:196-243`](app/services/job_service.py) | `search_jobs()` | Георадиус: total из БД ДО фильтрации — всегда завышен |

**Примечание:** [`nearby_jobs`](migrations/056_add_nearby_jobs_rpc.sql) RPC уже создан в миграции 056, но ещё не используется в коде.

---

### 2.3 In-memory состояние в multi-process окружении

**Приоритет: HIGH**

| # | Файл:Строка | Что хранится | Проблема |
|---|-------------|-------------|----------|
| 1 | [`email_service.py:45-46`](app/services/email_service.py) | `_daily_count`, `_last_reset_date` — дневной лимит email | Каждый Celery worker считает с 0. Лимит 1000/день не соблюдается |
| 2 | [`utils.py:575`](app/utils.py) | `rate_limit` декоратор — словарь в памяти | При нескольких worker'ах лимит 10 POST/60 сек на IP не работает |
| 3 | [`redis_publisher.py:33-73`](app/services/redis_publisher.py) | `self._client` — мёртвое соединение | После сбоя Redis соединение не восстанавливается — уведомления теряются навсегда |
| 4 | [`__init__.py:183-248`](app/__init__.py) | Контекст-процессоры `inject_unread_notifications`, `inject_pending_invitations` | HTTP-запрос к PostgREST на каждый запрос — нет кэша |

**Рекомендация:** Все счётчики и лимиты — в Redis (INCR + TTL). Для `rate_limit` — `redis-py` rate limiter. Для `redis_publisher` — сброс `self._client = None` в except-блоке.

---

### 2.4 Раздувание utils.py (монолит 66K)

**Приоритет: MEDIUM**

[`utils.py`](app/utils.py) содержит 1592 строки (66K символов) и смешивает несвязанные responsibilities:

| Группа | Строки | Что содержит | Куда перенести |
|--------|--------|-------------|----------------|
| Supabase HTTP-клиент | ~200 | `supabase_request()`, `supabase_admin_request()`, `supabase_rpc()`, CircuitBreaker | `app/services/supabase_client.py` |
| In-memory Mock Supabase | ~400 | Полная эмуляция REST API, Auth, RPC для тестов | `app/testing/mock_supabase.py` |
| Аутентификация | ~150 | `refresh_access_token()`, `get_user_role()`, `get_user_profile()` | `app/services/auth_service.py` |
| Загрузка файлов | ~100 | `upload_to_storage()`, `upload_photo()`, `delete_from_storage()` | `app/services/storage_service.py` |
| Геокодирование | ~80 | `geocode_address()`, `calculate_distance()` | `app/services/geo_service.py` |
| Рейтинги | ~60 | `update_rating()`, `get_user_rating()` | `app/services/ratings_service.py` |
| Утилиты | ~200 | `sanitize_postgrest()`, `format_currency()`, `paginate()` | `app/utils/` (разбить на модули) |
| Контекст-процессоры | ~100 | `inject_unread_notifications()`, `inject_ws_config()` | `app/context_processors.py` |
| Валидация | ~50 | `validate_password()`, `_SQL_INJECTION_PATTERNS` | `app/validators.py` |

**План расщепления:** Создать 9 целевых модулей, перенести функции с сохранением обратной совместимости через re-export в переходный период.

---

### 2.5 Дублирование кода

**Приоритет: MEDIUM**

| # | Паттерн | Где дублируется |
|---|---------|-----------------|
| 1 | Гео-фильтрация: `search_jobs()` и `search_workers()` — ~80% совпадения | [`job_service.py:202-225,266-287`](app/services/job_service.py) |
| 2 | Два механизма отзыва заявки: `unapply_job()` (DELETE) vs `api_withdraw_application()` (PATCH→withdrawn) | [`applications.py:250,268`](app/blueprints/applications.py) |
| 3 | Проверка роли вручную вместо `@role_required`: `my_jobs()`, `api_handle_application()`, accept/reject/reopen в [`__init__.py`](app/__init__.py) | 4 файла |
| 4 | Импорты внутри функций: `import traceback`, `import os`, `from datetime import date`, `from flask import current_app` | 8+ мест |
| 5 | `list_invitations()` в [`jobs_api.py:161-170`](app/blueprints/jobs_api.py) дублирует `invitations_page()` из [`jobs.py:730-743`](app/blueprints/jobs.py) | 2 файла |
| 6 | Чтение `os.environ` напрямую вместо `current_app.config`: EmailService, PushService | [`email_service.py:32-42`](app/services/email_service.py), [`push_service.py:49-56`](app/services/push_service.py) |
| 7 | Два эндпоинта верификации работодателя: `approve_employer()` (anon) и `verify_employer()` (admin) | [`admin.py:462-494`](app/blueprints/admin.py) |

---

### 2.6 Несогласованность документации и кода

**Приоритет: LOW**

| # | Документ | Расхождение |
|---|----------|-------------|
| 1 | [`PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) | Упоминает `shifts.py` blueprint (удалён), `config.py` в корне (удалён), Python 3.14 (реально 3.12), «10 Blueprints» (реально 13) |
| 2 | [`API_REFERENCE.md`](docs/API_REFERENCE.md) | Ссылается на `search.js`, `chat.js`, `notifications.js`, `invite.js`, `ratings.js`, `admin.js`, `employers.js` — не существуют в `static/js/` |
| 3 | [`SECURITY.md`](docs/SECURITY.md) | Упоминает Supabase Realtime (не используется), email verification (не реализован) |
| 4 | [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Упоминает `static/js/` файлы, которых нет в репозитории |

---

### 2.7 Хардкод секретов и паролей

**Приоритет: CRITICAL**

| # | Файл:Строка | Что захардкожено | Риск |
|---|-------------|------------------|------|
| 1 | [`amvera.yml:7`](amvera.yml) | `PGRST_JWT_SECRET=CHANGE_ME` — placeholder-секрет в Git | Компрометация JWT при утечке репозитория |
| 2 | [`test_buttons.py:37-44`](scripts/test_buttons.py) | Пароли `Step@1986`, `test123456`, `test123` | Компрометация тестовых аккаунтов |
| 3 | `_apply_all_direct.py`, `_create_base_tables.py`, `_create_email_log.py`, `_create_missing_tables.py`, `_init_exec_sql.py` | `DATABASE_URL` с паролем `postgres:postgres` | Доступ к БД при утечке |
| 4 | [`Dockerfile:34`](Dockerfile) | `USER appuser` закомментирован — контейнер от root | Нарушение least privilege |
| 5 | [`render.yaml:6`](render.yaml) | Скачивание tailwindcss бинарника без проверки хеша | Supply chain атака |

---

## 3. Топ-15 критических/высоких проблем (детально)

| # | Серьёзность | Файл:Строка | Проблема | Влияние | Рекомендация |
|---|------------|-------------|----------|---------|--------------|
| 1 | **CRITICAL** | [`amvera.yml:7`](amvera.yml) | `PGRST_JWT_SECRET=CHANGE_ME` закоммичен в репозиторий | Компрометация всех JWT-токенов при утечке кода | Удалить из файла, задавать через Amvera Secrets |
| 2 | **CRITICAL** | [`apply_new_migrations.py:73-81`](scripts/apply_new_migrations.py) | Прямая модификация `pg_catalog.pg_proc` через UPDATE с конкатенацией строк | Разрушение системного каталога PostgreSQL | Переписать через `CREATE OR REPLACE FUNCTION` |
| 3 | **CRITICAL** | [`Dockerfile:1`](Dockerfile) | `FROM python:3.11-slim` — код использует синтаксис Python 3.12+ (`str \| None`) | Образ несовместим с кодом — приложение не запустится | `FROM python:3.12-slim` |
| 4 | **CRITICAL** | [`applications.py:187-243`](app/blueprints/applications.py) | `apply_selected()` обходит RPC `apply_job_atomic` — нет проверок blacklist, слотов, своего задания | Заблокированный трудник обходит блокировку | Заменить на `supabase_rpc("apply_job_atomic")` |
| 5 | **CRITICAL** | [`Dockerfile:34`](Dockerfile) | `USER appuser` закомментирован — контейнер от root | Нарушение принципа наименьших привилегий | Раскомментировать, порт >1024 |
| 6 | **HIGH** | [`jobs.py:126-185`](app/blueprints/jobs.py) | Фильтрация после limit/offset — страницы неравномерны, данные пропускаются | Пользователи видят неполные/пустые страницы результатов | Перенести фильтры в SQL/RPC, использовать `nearby_jobs` |
| 7 | **HIGH** | [`applications.py:280-362`](app/blueprints/applications.py) | `api_withdraw_application()` — 6 неатомарных HTTP-запросов | `current_workers` уходит в минус при параллельных запросах | Создать RPC `withdraw_application_atomic` |
| 8 | **HIGH** | [`applications.py:571-637`](app/blueprints/applications.py) | `cancel_application()` — 5 неатомарных запросов, нет проверки статуса | Двойная отмена → отрицательный `current_workers` | Создать RPC `cancel_worker_atomic` |
| 9 | **HIGH** | [`jobs.py:553-565`](app/blueprints/jobs.py) | `cancel_job()` — race condition между проверкой accepted и отменой | Отмена задания с accepted-откликами | Создать RPC `cancel_job_atomic` |
| 10 | **HIGH** | [`jobs_api.py:206-223`](app/blueprints/jobs_api.py) | Принятие приглашения bypass'ит бизнес-правила `apply_job_atomic` | Трудник принят на заполненное задание | Использовать `apply_job_atomic` RPC |
| 11 | **HIGH** | [`email_service.py:45-46`](app/services/email_service.py) | Дневной лимит в памяти экземпляра — не работает в multi-worker | Лимит 1000/день не соблюдается | Redis INCR + EXPIRE до полуночи |
| 12 | **HIGH** | [`redis_publisher.py:33-73`](app/services/redis_publisher.py) | Мёртвое Redis-соединение не восстанавливается | Все real-time уведомления теряются после сбоя Redis | `self._client = None` в except-блоке |
| 13 | **HIGH** | [`push_service.py:326-330`](app/services/push_service.py) | `delete_subscription()` — нет проверки `user_id` | Можно удалить чужую push-подписку | Добавить `user_id` параметр и фильтр |
| 14 | **HIGH** | [`push_service.py:157`](app/services/push_service.py) | `vapid_claims[exp]` — строка `"24h"` вместо Unix timestamp (RFC 8292) | Push-серверы могут отклонять уведомления | `int(time.time()) + 86400` |
| 15 | **HIGH** | [`notification_service.py:234-236`](app/services/notification_service.py) | `get_unread_count()` с `limit=100` — недоучёт при >100 | Пользователь видит неверный счётчик | `Prefer: count=exact`, `limit=0` |

---

## 4. План рефакторинга (по приоритетам)

### Фаза 1: Критические исправления (должны быть сделаны до любого деплоя)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 1 | Убрать закоммиченный секрет | [`amvera.yml:7`](amvera.yml) | Удалить `PGRST_JWT_SECRET=CHANGE_ME`, добавить инструкцию по установке через Amvera Secrets |
| 2 | Переписать модификацию `pg_catalog` | [`apply_new_migrations.py:73-81`](scripts/apply_new_migrations.py) | Заменить `UPDATE pg_catalog.pg_proc` на `CREATE OR REPLACE FUNCTION` |
| 3 | Исправить версию Python в Dockerfile | [`Dockerfile:1`](Dockerfile) | `FROM python:3.12-slim` |
| 4 | Включить non-root пользователя | [`Dockerfile:34`](Dockerfile) | Раскомментировать `USER appuser`, порт >1024 |
| 5 | Исправить `apply_selected()` — обход бизнес-правил | [`applications.py:187-243`](app/blueprints/applications.py) | Заменить на `supabase_rpc("apply_job_atomic")` в цикле |
| 6 | Убрать хардкод паролей в тестовых скриптах | [`test_buttons.py:37-44`](scripts/test_buttons.py), `_*.py` | Перенести в переменные окружения |
| 7 | Убрать `USER appuser` закомментированность | [`Dockerfile:34`](Dockerfile) | Раскомментировать |
| 8 | Добавить проверку хеша для tailwindcss | [`render.yaml:6`](render.yaml) | Добавить `sha256sum` проверку |

### Фаза 2: Высокий приоритет (исправить в ближайшем спринте)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 1 | Создать RPC `withdraw_application_atomic` | Миграция 059 | Атомарный отзыв: проверка статуса + декремент `current_workers` + PATCH статуса заявки |
| 2 | Создать RPC `cancel_worker_atomic` | Миграция 059 | Атомарная отмена: проверка accepted + декремент + PATCH |
| 3 | Создать RPC `cancel_job_atomic` | Миграция 059 | Проверка accepted-откликов + отмена задания в одной транзакции |
| 4 | Создать RPC `force_complete_job` | Миграция 059 | Атомарный reject всех pending + установка completed |
| 5 | Создать RPC `accept_invitation_atomic` | Миграция 059 | Принятие приглашения через `apply_job_atomic` + обновление приглашения |
| 6 | Исправить пагинацию в `index()` | [`jobs.py:126-185`](app/blueprints/jobs.py) | Перенести фильтры в SQL, использовать `nearby_jobs` RPC для гео |
| 7 | Исправить пагинацию в `employers_list()` | [`employers.py:46-78`](app/blueprints/employers.py) | Фильтрация blacklist на стороне БД |
| 8 | Исправить пагинацию в `search_jobs()` | [`job_service.py:196-243`](app/services/job_service.py) | Использовать `nearby_jobs` RPC для гео-фильтрации |
| 9 | Перенести дневной лимит email в Redis | [`email_service.py:45-46`](app/services/email_service.py) | `Redis INCR email:daily:YYYY-MM-DD` + `EXPIRE` до полуночи |
| 10 | Исправить восстановление Redis-соединения | [`redis_publisher.py:33-73`](app/services/redis_publisher.py) | `self._client = None` в except-блоке `publish()` |
| 11 | Добавить `user_id` проверку в `delete_subscription()` | [`push_service.py:326-330`](app/services/push_service.py) | `delete_subscription(user_id, endpoint)` |
| 12 | Исправить формат VAPID expiration | [`push_service.py:157`](app/services/push_service.py) | `int(time.time()) + 86400` |
| 13 | Исправить `get_unread_count()` | [`notification_service.py:234-236`](app/services/notification_service.py) | `Prefer: count=exact`, `limit=0` |
| 14 | Добавить `user_id` в `mark_read()` | [`notification_service.py:246-249`](app/services/notification_service.py) | `notifications?id=eq.{id}&user_id=eq.{user_id}` |
| 15 | Исправить `NameError` в `auth.py` | [`auth.py:238-244`](app/blueprints/auth.py) | Инициализировать `err_data = None` до try |
| 16 | Исправить неатомарный accept rejected | [`applications.py:437-441`](app/blueprints/applications.py) | Перенести rejected→pending внутрь RPC `accept_application` |
| 17 | Защитить админа от само-лок-аута | [`admin.py:100`](app/blueprints/admin.py) | `if user_id == session["user_id"]: flash(...); redirect(...)` |
| 18 | Добавить REVOKE EXECUTE в миграцию 058 | [`058_add_native_auth.sql:13,26,40`](migrations/058_add_native_auth.sql) | `REVOKE EXECUTE FROM anon, PUBLIC` для всех трёх RPC |
| 19 | Исправить `cancel_application()` — проверка статуса | [`applications.py:571-637`](app/blueprints/applications.py) | `if status != 'accepted': flash('Нельзя отменить', 'danger'); return` |
| 20 | Добавить SMTP connection pooling | [`email_service.py:124-142`](app/services/email_service.py) | Ленивое соединение как атрибут экземпляра |

### Фаза 3: Средний приоритет (в течение месяца)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 1 | Расщепить `utils.py` | [`utils.py`](app/utils.py) | Разделить на 9 модулей (см. таблицу в §2.4) |
| 2 | Создать `ApplicationService` | Новый файл | Вынести бизнес-логику откликов из [`applications.py`](app/blueprints/applications.py) |
| 3 | Унифицировать отзыв заявки | [`applications.py`](app/blueprints/applications.py) | Оставить один механизм (withdraw через RPC) |
| 4 | Унифицировать декораторы vs ручные проверки | 4 файла | Все защищённые эндпоинты — через `@role_required` |
| 5 | Вынести `os.environ` в параметры конструкторов | [`email_service.py`](app/services/email_service.py), [`push_service.py`](app/services/push_service.py) | Принимать настройки через `__init__` |
| 6 | Убрать дублирование гео-фильтрации | [`job_service.py`](app/services/job_service.py) | Извлечь `_apply_geo_filters()` |
| 7 | Заменить `send_batch()` синхронный цикл на Celery group | [`email_service.py:179-212`](app/services/email_service.py) | `celery.group(send_email.s(...) for r in recipients).apply_async()` |
| 8 | Исправить загрузку всех подписок в память | [`push_service.py:359-366`](app/services/push_service.py) | Пагинация с limit/offset |
| 9 | Добавить пагинацию в `my_applications()` | [`applications.py:376-378`](app/blueprints/applications.py) | `limit=50&offset=...` |
| 10 | Исправить подсчёт статистики дашборда | [`admin.py:27,35`](app/blueprints/admin.py) | `count` без limit или RPC |
| 11 | Убрать дублирующие запросы в `my_jobs()` | [`jobs.py:455-474`](app/blueprints/jobs.py) | Оставить только batch-запрос |
| 12 | Кэшировать `inject_application_count()` | [`jobs.py:81-85`](app/blueprints/jobs.py) | Redis TTL 30 сек |
| 13 | Кэшировать `inject_unread_notifications` | [`__init__.py:183-248`](app/__init__.py) | Redis TTL 30 сек |
| 14 | Вынести очистку orphaned-уведомлений в Celery | [`notifications.py:36-41`](app/blueprints/notifications.py) | Периодическая задача раз в час |
| 15 | Добавить колонку `job_id` в `notifications` | Миграция | Везде, где используется `ilike.*job_id*` |

### Фаза 4: Низкий приоритет (когда будет время)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 1 | Обновить [`PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) | Документация | Исправить количество blueprint'ов, версию Python, удалить `shifts.py` |
| 2 | Обновить [`API_REFERENCE.md`](docs/API_REFERENCE.md) | Документация | Актуализировать список JS-файлов |
| 3 | Добавить валидацию UUID во всех blueprint'ах | 5 файлов | Декоратор `@validate_uuid` |
| 4 | Добавить проверку `resp.ok` во всех эндпоинтах | 6 файлов | Утилита `assert_supabase_ok(resp, error_message)` |
| 5 | Убрать локальные импорты внутри функций | 8+ мест | Перенести на уровень модуля |
| 6 | Унифицировать HTTP-клиенты в скриптах | 5 скриптов | Заменить `requests` на `httpx` |
| 7 | Добавить `--down` секции в миграции | 58 миграций | Хотя бы для миграций, меняющих типы колонок |
| 8 | Унифицировать `FLASK_ENV` → `DEPLOYMENT_ENV` | [`config.py:15-28`](app/config.py) | Избавиться от deprecated `FLASK_ENV` |
| 9 | Удалить неиспользуемые зависимости | [`requirements.txt`](requirements.txt) | openai, Flask-Login, gunicorn, fpdf2 |
| 10 | Добавить `HEALTHCHECK` в Dockerfile | [`Dockerfile`](Dockerfile) | `HEALTHCHECK CMD curl -f http://localhost:$PORT/health` |
| 11 | Исправить несуществующие колонки в cleanup/preseed | [`cleanup_test_data.py`](scripts/cleanup_test_data.py), [`preseed_test_data.py`](scripts/preseed_test_data.py) | Сверить имена колонок с актуальной схемой |
| 12 | Переименовать дубликат номера миграции 019 | Миграции | `019b_fix_security_warnings.sql` |
| 13 | Убрать авто-отметку уведомлений прочитанными | [`notifications.py:43-46`](app/blueprints/notifications.py) | Отмечать только при явном действии |
| 14 | Исправить проверку чата только для completed-заданий | [`chat.py:122-132`](app/blueprints/chat.py) | Разрешить чат для accepted-заявок |
| 15 | Добавить `favorite_type` в `check_favorite_api` | [`favorites.py:116`](app/blueprints/favorites.py) | `&favorite_type=eq.worker` |
| 16 | Унифицировать `VERSION` на SemVer | [`VERSION`](VERSION) | `MAJOR.MINOR.PATCH` |

---

## 5. Рекомендуемые архитектурные улучшения

### 5.1 Расщепление utils.py

См. таблицу в §2.4. Целевая структура:
```
app/
  services/
    supabase_client.py    # supabase_request, supabase_admin_request, supabase_rpc, CircuitBreaker
    auth_service.py       # refresh_access_token, get_user_role, get_user_profile
    storage_service.py    # upload_to_storage, upload_photo, delete_from_storage
    geo_service.py        # geocode_address, calculate_distance
    ratings_service.py    # update_rating, get_user_rating
  utils/
    __init__.py           # re-export для обратной совместимости
    postgrest.py          # sanitize_postgrest
    formatting.py         # format_currency, format_date
    pagination.py         # paginate
    validators.py         # validate_password, SQL injection patterns
  context_processors.py   # inject_unread_notifications, inject_ws_config, inject_pending_invitations
  testing/
    mock_supabase.py      # In-memory Mock Supabase
```

### 5.2 Введение репозиториев для Supabase-запросов

Выделить слой доступа к данным (Data Access Layer) для стандартизации запросов к PostgREST:

```python
class JobRepository:
    def find_by_id(self, job_id) -> dict
    def search(self, filters: JobSearchFilters) -> PaginatedResult
    def update(self, job_id, data) -> bool

class ApplicationRepository:
    def find_by_id(self, app_id) -> dict
    def find_by_job_and_worker(self, job_id, worker_id) -> dict
    def update_status(self, app_id, status) -> bool
```

Это устранит разрозненные `supabase_request` вызовы в blueprint'ах и позволит централизованно применять валидацию, логирование и обработку ошибок.

### 5.3 Создание недостающих RPC-функций

10 RPC-функций из списка в §2.1 должны быть созданы в первую очередь (см. Фазу 2 плана рефакторинга). Каждая RPC должна:

- Использовать `SECURITY DEFINER`
- Устанавливать `search_path = public`
- Проверять все бизнес-правила внутри транзакции
- Возвращать структурированный JSON с `success`, `error`, `data`
- Иметь `REVOKE EXECUTE FROM anon, PUBLIC; GRANT EXECUTE TO authenticated, service_role;`

### 5.4 Унификация обработки ошибок

Создать централизованный обработчик ошибок для всех взаимодействий с Supabase:

```python
def assert_supabase_ok(resp, operation: str, context: dict = None) -> None:
    """Проверяет успешность ответа Supabase, логирует и райзит при ошибке."""
    if not resp.ok:
        logger.error(f"Supabase {operation} failed", extra={
            'status_code': resp.status_code,
            'error': resp.text,
            'context': context
        })
        raise SupabaseError(f"{operation} failed: {resp.status_code}")
```

Использовать во всех blueprint'ах вместо разрозненных проверок.

### 5.5 Централизованная валидация входных данных

Создать декоратор `@validate_uuid` для параметров маршрута:

```python
def validate_uuid(*param_names: str):
    """Проверяет, что указанные параметры маршрута являются валидными UUID."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for name in param_names:
                if name in kwargs:
                    try:
                        uuid.UUID(kwargs[name])
                    except ValueError:
                        flash(f'Некорректный идентификатор: {name}', 'danger')
                        return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

### 5.6 Dependency Injection для сервисов

Создать единый паттерн инициализации сервисов через `app.extensions`:

```python
# В create_app():
app.extensions['email_service'] = EmailService(
    smtp_host=app.config['SMTP_HOST'],
    smtp_port=app.config['SMTP_PORT'],
    ...
)
app.extensions['push_service'] = PushService(
    vapid_private_key=app.config['VAPID_PRIVATE_KEY'],
    ...
)

# В blueprint'ах:
email_service = current_app.extensions['email_service']
```

Это устранит чтение `os.environ` напрямую из сервисов и упростит тестирование.

---

## 6. Метрики качества кода

| Метрика | Текущее | Целевое |
|---------|---------|---------|
| Размер utils.py | 1592 строки (66K) | <500 строк |
| Количество модулей utils | 1 | 9 |
| Покрытие RLS | ~85% (80+ политик, 21 активная таблица) | 100% |
| Неатомарных операций | ~15 | 0 |
| Недостающих RPC | 10 | 0 |
| Дубликатов номера миграций | 1 (019) | 0 |
| Хардкод секретов в репозитории | 5+ | 0 |
| In-memory состояния в multi-process | 4 | 0 |
| Эндпоинтов с неработающей пагинацией | 3 | 0 |
| Зависимостей с открытым верхним пределом версий | 6 | 0 |
| Неиспользуемых зависимостей | 4 (openai, Flask-Login, gunicorn, fpdf2) | 0 |
| Эндпоинтов без `@role_required` | 5 | 0 |
| Эндпоинтов без проверки `resp.ok` | ~15 | 0 |
| Файлов с хардкодом URL/паролей | 7 | 0 |
| Миграций с BEGIN/COMMIT | 3 из 58 | Все новые |
| Миграций с `--down` секциями | 0 из 58 | Для деструктивных |

---

## 7. Заключение

### Общая оценка

Проект «Трудник» демонстрирует зрелый уровень архитектурного мышления: чёткое разделение на blueprint'ы, сервисный слой, использование RPC для атомарных операций, RLS на уровне БД. Однако накопленный технический долг в виде 348 проблем (5 CRITICAL, 54 HIGH) требует системного подхода к устранению.

### Основные риски

1. **Целостность данных.** 15 неатомарных операций угрожают консистентности БД при параллельных запросах. `current_workers` может уйти в минус, оценки — рассинхронизироваться, задания — остаться в несогласованном состоянии.

2. **Безопасность.** Закоммиченный JWT-секрет, обход бизнес-правил в `apply_selected()`, отсутствие проверки владельца в `delete_subscription()` и `mark_read()`, контейнер от root — каждый из этих векторов может привести к компрометации данных.

3. **Надёжность.** Дневной лимит email не работает в multi-worker, мёртвое Redis-соединение не восстанавливается, сломана пагинация — эти проблемы напрямую влияют на пользовательский опыт.

4. **Сопровождаемость.** Монолитный `utils.py` (66K), разрозненные проверки ошибок, неиспользуемые зависимости, устаревшая документация — всё это замедляет разработку и onboarding новых разработчиков.

### Светлые стороны

- 8 работающих RPC-процедур доказывают правильность подхода
- 58 идемпотентных миграций с покрытием RLS
- Circuit Breaker защищает от каскадных отказов
- Полноценный in-memory Mock Supabase для тестирования
- Чёткая файловая структура и нейминг

### Рекомендации по процессам

1. **Ввести pre-commit хук** для проверки хардкода секретов (detect-secrets, gitleaks)
2. **Все новые мутации — только через RPC.** Никаких последовательных HTTP-запросов для составных операций
3. **Ввести обязательное ревью для миграций**, меняющих типы колонок или удаляющих данные
4. **Добавить `--down` секции** во все новые деструктивные миграции
5. **Обновить документацию** после каждого значительного изменения (синхронизировать с кодом)
6. **Внедрить мониторинг:** алерты на ошибки Supabase, Circuit Breaker срабатывания, Redis disconnect

### Итоговая оценка

**APPROVE WITH CRITICAL CHANGES REQUIRED** — 5 критических проблем должны быть устранены до следующего деплоя в production. Фаза 2 (20 HIGH-проблем) должна быть выполнена в ближайшем спринте. После этого проект будет в стабильном, безопасном и сопровождаемом состоянии.

---

*Отчёт создан в рамках Этапа 8 комплексного код-ревью.*
*Все исходные отчёты этапов доступны в `docs/CODE_REVIEW_STAGE*.md`.*
