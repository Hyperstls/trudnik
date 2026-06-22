# Список задач рефакторинга (Фазы 2-4)

> Извлечено из [`CODE_REVIEW_FINAL_REPORT.md`](docs/CODE_REVIEW_FINAL_REPORT.md), раздел 4 «План рефакторинга»
> Дата: 2026-06-22

---

## Фаза 2: HIGH (20 задач) — ближайший спринт

### 2.1 Создание RPC-процедур (5 задач)

| # | RPC | Файл миграции | Описание |
|---|-----|---------------|----------|
| 1 | `withdraw_application_atomic` | `migrations/059_*.sql` | Атомарный отзыв заявки: проверка статуса + декремент `current_workers` + PATCH статуса. Замена 6 неатомарных HTTP-запросов в [`applications.py:280-362`](app/blueprints/applications.py) |
| 2 | `cancel_worker_atomic` | `migrations/059_*.sql` | Атомарная отмена работника: проверка `status='accepted'` + декремент `current_workers` + PATCH. Замена 5 запросов в [`applications.py:571-637`](app/blueprints/applications.py) |
| 3 | `cancel_job_atomic` | `migrations/059_*.sql` | Проверка accepted-откликов (GET) + отмена задания (PATCH) в одной транзакции. Замена race condition в [`jobs.py:553-565`](app/blueprints/jobs.py) |
| 4 | `force_complete_job` | `migrations/059_*.sql` | Атомарный reject всех pending-откликов + установка `status='completed'`. Замена двух неатомарных операций в [`jobs.py:663-668`](app/blueprints/jobs.py) |
| 5 | `accept_invitation_atomic` | `migrations/059_*.sql` | Принятие приглашения: создание заявки через `apply_job_atomic` + обновление статуса приглашения. Замена неатомарных POST+PATCH в [`jobs_api.py:206-223`](app/blueprints/jobs_api.py) |

**Требования к каждой RPC:**
- `SECURITY DEFINER` с `search_path = public`
- Проверка всех бизнес-правил внутри транзакции
- Возврат структурированного JSON: `{success, error, data}`
- `REVOKE EXECUTE FROM anon, PUBLIC; GRANT EXECUTE TO authenticated, service_role;`

---

### 2.2 Исправление пагинации (3 задачи)

| # | Файл:Строки | Эндпоинт | Проблема | Действие |
|---|-------------|----------|----------|----------|
| 6 | [`jobs.py:126-185`](app/blueprints/jobs.py) | `index()` — главная лента | Фильтрация в Python ПОСЛЕ `limit/offset`: статус, expires_at, blacklist, навыки, радиус | Перенести все фильтры в SQL. Для гео-фильтрации использовать существующий RPC `nearby_jobs` (миграция 056) |
| 7 | [`employers.py:46-78`](app/blueprints/employers.py) | `employers_list()` | Фильтрация blacklist в Python после пагинации; `total_pages` вычислен от уже отфильтрованного | Фильтровать blacklist на стороне БД через подзапрос `NOT IN` |
| 8 | [`job_service.py:196-243`](app/services/job_service.py) | `search_jobs()` | Георадиус: `total` из БД ДО Python-фильтрации — всегда завышен | Использовать RPC `nearby_jobs` для гео-фильтрации на стороне БД |

---

### 2.3 Redis вместо in-memory (4 задачи)

| # | Файл:Строки | Проблема | Действие |
|---|-------------|----------|----------|
| 9 | [`email_service.py:45-46`](app/services/email_service.py) | `_daily_count`, `_last_reset_date` — in-memory счётчик дневного лимита. Каждый Celery worker считает с 0, лимит 1000/день не соблюдается | `Redis INCR email:daily:YYYY-MM-DD` + `EXPIRE` до полуночи следующего дня |
| 10 | [`redis_publisher.py:33-73`](app/services/redis_publisher.py) | `self._client` становится мёртвым после сбоя Redis, соединение не восстанавливается — все real-time уведомления теряются | `self._client = None` в except-блоке метода `publish()` для автоматического переподключения |
| 11 | [`utils.py:575`](app/utils.py) | `rate_limit` декоратор — словарь в памяти. При нескольких worker'ах лимит 10 POST/60 сек на IP не работает | Redis rate limiter: `INCR` + `TTL` на ключ `ratelimit:<ip>:<endpoint>` |
| 12 | [`__init__.py:183-248`](app/__init__.py) | Контекст-процессоры `inject_unread_notifications`, `inject_pending_invitations` — HTTP-запрос к PostgREST на каждый запрос, без кэша | Кэшировать в Redis с TTL 30 сек; инвалидировать при изменении |

---

### 2.4 Уязвимости push/notifications (4 задачи)

| # | Файл:Строки | Проблема | Действие |
|---|-------------|----------|----------|
| 13 | [`push_service.py:326-330`](app/services/push_service.py) | `delete_subscription()` — нет проверки `user_id`, можно удалить чужую push-подписку | Добавить параметр `user_id` и фильтр `&user_id=eq.{user_id}` в URL удаления |
| 14 | [`push_service.py:157`](app/services/push_service.py) | `vapid_claims[exp]` — строка `"24h"` вместо Unix timestamp (RFC 8292). Push-серверы могут отклонять уведомления | `int(time.time()) + 86400` |
| 15 | [`notification_service.py:234-236`](app/services/notification_service.py) | `get_unread_count()` с `limit=100` — недоучёт непрочитанных при количестве >100 | Использовать заголовок `Prefer: count=exact` и `limit=0` для получения точного количества |
| 16 | [`notification_service.py:246-249`](app/services/notification_service.py) | `mark_read()` — нет проверки `user_id`, можно пометить чужие уведомления прочитанными | Добавить фильтр `&user_id=eq.{user_id}` к URL: `notifications?id=eq.{id}&user_id=eq.{user_id}` |

---

### 2.5 Неатомарные операции в blueprint'ах (4 задачи)

| # | Файл:Строки | Проблема | Действие |
|---|-------------|----------|----------|
| 17 | [`applications.py:437-441`](app/blueprints/applications.py) | Accept rejected-заявки: PATCH `rejected→pending` выполняется вне RPC `accept_application`. При сбое между PATCH и RPC — потеря данных | Перенести rejected→pending transition внутрь RPC `accept_application` |
| 18 | [`applications.py:571-637`](app/blueprints/applications.py) | `cancel_application()` — 5 неатомарных запросов: GET→GET→GET→PATCH→PATCH. Нет проверки текущего статуса, двойная отмена → `current_workers` в минус | Добавить проверку: `if status != 'accepted': flash('Нельзя отменить', 'danger'); return`. Использовать RPC `cancel_worker_atomic` (задача #2) |
| 19 | [`auth.py:238-244`](app/blueprints/auth.py) | `NameError` при ошибке валидации: `err_data` используется, но не инициализирован до `try` блока | Инициализировать `err_data = None` до `try` |
| 20 | [`admin.py:100`](app/blueprints/admin.py) | `update_user_role()` — администратор может лишить себя прав админа (само-лок-аут) | Добавить проверку: `if user_id == session["user_id"]: flash('Нельзя изменить свою роль', 'danger'); redirect(...)` |

**Дополнительно (входит в Фазу 2, вне подкатегорий):**

| # | Файл:Строки | Проблема | Действие |
|---|-------------|----------|----------|
| 21 | [`email_service.py:124-142`](app/services/email_service.py) | SMTP соединение создаётся заново при каждой отправке — накладные расходы | Ленивое соединение как атрибут экземпляра (connection pooling) |
| 22 | [`058_add_native_auth.sql:13,26,40`](migrations/058_add_native_auth.sql) | Новые RPC в миграции 058 не имеют `REVOKE EXECUTE` — доступны анонимам | Добавить `REVOKE EXECUTE FROM anon, PUBLIC` для всех трёх RPC функций |

---

## Фаза 3: MEDIUM (15 задач) — в течение месяца

### 3.1 Расщепление монолита (3 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 23 | Расщепить [`utils.py`](app/utils.py) (1592 строки, 66K) | [`utils.py`](app/utils.py) | Разделить на 9 модулей согласно плану в §2.4 отчёта: `supabase_client.py`, `auth_service.py`, `storage_service.py`, `geo_service.py`, `ratings_service.py`, `utils/postgrest.py`, `utils/formatting.py`, `utils/pagination.py`, `validators.py`, `context_processors.py` |
| 24 | Создать `ApplicationService` | Новый файл `app/services/application_service.py` | Вынести бизнес-логику откликов из [`applications.py`](app/blueprints/applications.py): валидация, проверка слотов, blacklist |
| 25 | Унифицировать отзыв заявки | [`applications.py`](app/blueprints/applications.py) | Оставить один механизм отзыва: `api_withdraw_application()` → RPC `withdraw_application_atomic`. Удалить старый `unapply_job()` (DELETE) |

### 3.2 Устранение дублирования (4 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 26 | Унифицировать декораторы vs ручные проверки ролей | [`jobs.py`](app/blueprints/jobs.py), [`jobs_api.py`](app/blueprints/jobs_api.py), [`applications.py`](app/blueprints/applications.py), [`__init__.py`](app/__init__.py) | Все защищённые эндпоинты — через `@role_required`. Убрать ручные проверки `session.get("user_role")` в `my_jobs()`, `api_handle_application()`, accept/reject/reopen |
| 27 | Вынести `os.environ` в параметры конструкторов | [`email_service.py:32-42`](app/services/email_service.py), [`push_service.py:49-56`](app/services/push_service.py) | Принимать настройки SMTP/VAPID через `__init__()`, брать из `current_app.config` |
| 28 | Убрать дублирование гео-фильтрации | [`job_service.py:202-225,266-287`](app/services/job_service.py) | Извлечь общую функцию `_apply_geo_filters()`. `search_jobs()` и `search_workers()` имеют ~80% совпадения кода |
| 29 | Убрать дублирование `list_invitations()` | [`jobs_api.py:161-170`](app/blueprints/jobs_api.py), [`jobs.py:730-743`](app/blueprints/jobs.py) | Оставить один источник; `invitations_page()` и `list_invitations()` делают одно и то же |

### 3.3 Оптимизация производительности (5 задач)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 30 | Заменить `send_batch()` синхронный цикл на Celery group | [`email_service.py:179-212`](app/services/email_service.py) | `celery.group(send_email.s(...) for r in recipients).apply_async()` |
| 31 | Исправить загрузку всех push-подписок в память | [`push_service.py:359-366`](app/services/push_service.py) | Добавить пагинацию с `limit/offset` при получении списка подписок |
| 32 | Добавить пагинацию в `my_applications()` | [`applications.py:376-378`](app/blueprints/applications.py) | `limit=50&offset=...` вместо загрузки всех заявок пользователя |
| 33 | Исправить подсчёт статистики дашборда | [`admin.py:27,35`](app/blueprints/admin.py) | Использовать `Prefer: count=exact` с `limit=0` или RPC для получения точных count без лимита |
| 34 | Убрать дублирующие запросы в `my_jobs()` | [`jobs.py:455-474`](app/blueprints/jobs.py) | Оставить только batch-запрос, убрать лишние индивидуальные запросы |

### 3.4 Кэширование и Celery (3 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 35 | Кэшировать `inject_application_count()` | [`jobs.py:81-85`](app/blueprints/jobs.py) | Redis TTL 30 сек; инвалидировать при новом отклике/отзыве |
| 36 | Кэшировать `inject_unread_notifications` | [`__init__.py:183-248`](app/__init__.py) | Redis TTL 30 сек; инвалидировать при создании/прочтении уведомления |
| 37 | Вынести очистку orphaned-уведомлений в Celery | [`notifications.py:36-41`](app/blueprints/notifications.py) | Периодическая задача раз в час: удалять уведомления, ссылающиеся на несуществующие задания/заявки |
| 38 | Добавить колонку `job_id` в таблицу `notifications` | Миграция | Везде, где используется `metadata->>'job_id'` или `ilike '%job_id%'` — заменить на прямую колонку с индексом |

---

## Фаза 4: LOW (16 задач) — когда будет время

### 4.1 Документация (2 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 39 | Обновить [`PROJECT_CONTEXT.md`](docs/PROJECT_CONTEXT.md) | Документация | Исправить: количество blueprint'ов (13, не 10), версию Python (3.12, не 3.14), удалить упоминания `shifts.py` и `config.py` в корне |
| 40 | Обновить [`API_REFERENCE.md`](docs/API_REFERENCE.md) | Документация | Актуализировать список JS-файлов: удалить ссылки на `search.js`, `chat.js`, `notifications.js`, `invite.js`, `ratings.js`, `admin.js`, `employers.js` |

### 4.2 Валидация и безопасность (3 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 41 | Добавить валидацию UUID во всех blueprint'ах | 5 файлов: [`jobs.py`](app/blueprints/jobs.py), [`applications.py`](app/blueprints/applications.py), [`profile.py`](app/blueprints/profile.py), [`ratings.py`](app/blueprints/ratings.py), [`chat.py`](app/blueprints/chat.py) | Создать декоратор `@validate_uuid('job_id', 'user_id')` с проверкой `uuid.UUID()` и flash+redirect при ошибке |
| 42 | Добавить проверку `resp.ok` во всех эндпоинтах | 6 файлов | Создать утилиту `assert_supabase_ok(resp, error_message)` и применить во всех вызовах `supabase_request` |
| 43 | Исправить проверку чата — разрешить для accepted-заявок | [`chat.py:122-132`](app/blueprints/chat.py) | Сейчас чат доступен только для `completed` заданий; должно быть также для `accepted`-заявок |

### 4.3 Инфраструктура и конфигурация (5 задач)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 44 | Унифицировать `FLASK_ENV` → `DEPLOYMENT_ENV` | [`config.py:15-28`](app/config.py) | Избавиться от deprecated `FLASK_ENV`, использовать собственное имя переменной |
| 45 | Удалить неиспользуемые зависимости | [`requirements.txt`](requirements.txt) | Удалить: `openai`, `Flask-Login`, `gunicorn`, `fpdf2` |
| 46 | Добавить `HEALTHCHECK` в Dockerfile | [`Dockerfile`](Dockerfile) | `HEALTHCHECK --interval=30s CMD curl -f http://localhost:$PORT/health \|\| exit 1` |
| 47 | Переименовать дубликат номера миграции 019 | Миграции | `019_fix_missing_notifications_columns.sql` и `019_fix_security_warnings.sql` → переименовать вторую в `019b_fix_security_warnings.sql` |
| 48 | Унифицировать `VERSION` на SemVer | [`VERSION`](VERSION) | Привести к формату `MAJOR.MINOR.PATCH` (сейчас нестандартный формат) |

### 4.4 Качество кода (4 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 49 | Убрать локальные импорты внутри функций | 8+ мест | Перенести `import traceback`, `import os`, `from datetime import date`, `from flask import current_app` на уровень модуля |
| 50 | Унифицировать HTTP-клиенты в скриптах | 5 скриптов: `_apply_all_direct.py`, `_create_base_tables.py`, `_create_email_log.py`, `_create_missing_tables.py`, `_init_exec_sql.py` | Заменить `requests` на `httpx` (асинхронный, используется в проекте) |
| 51 | Добавить `--down` секции в миграции | 58 миграций | Хотя бы для миграций, меняющих типы колонок или структуру таблиц |
| 52 | Исправить несуществующие колонки в cleanup/preseed | [`cleanup_test_data.py`](scripts/cleanup_test_data.py), [`preseed_test_data.py`](scripts/preseed_test_data.py) | Сверить имена колонок с актуальной схемой БД |

### 4.5 UX и поведение (2 задачи)

| # | Задача | Файл | Действие |
|---|--------|------|----------|
| 53 | Убрать авто-отметку уведомлений прочитанными | [`notifications.py:43-46`](app/blueprints/notifications.py) | Отмечать уведомления прочитанными только при явном действии пользователя |
| 54 | Добавить `favorite_type` в `check_favorite_api` | [`favorites.py:116`](app/blueprints/favorites.py) | Добавить фильтр `&favorite_type=eq.worker` в запрос для точного различения типов избранного |

---

## Сводная таблица

| Фаза | Приоритет | Задач | Срок |
|------|-----------|-------|------|
| Фаза 2 | HIGH | 22 | Ближайший спринт |
| Фаза 3 | MEDIUM | 16 | В течение месяца |
| Фаза 4 | LOW | 16 | Когда будет время |
| **Итого** | | **54** | |

> **Примечание:** Фаза 1 (CRITICAL, 8 задач) описана в [`CODE_REVIEW_FINAL_REPORT.md`](docs/CODE_REVIEW_FINAL_REPORT.md) §4, строки 196-207. Она должна быть выполнена до любого деплоя и в данный файл не включена.
