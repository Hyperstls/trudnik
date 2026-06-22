# Этап 2-A: Ревью ключевых blueprint'ов

> **Дата:** 2026-06-22 | **Контекст:** [`CODE_REVIEW_CONTEXT.md`](docs/CODE_REVIEW_CONTEXT.md), [`CODE_REVIEW_STAGE1_INFRA.md`](docs/CODE_REVIEW_STAGE1_INFRA.md)  
> **Охват:** 3 файла — [`app/blueprints/auth.py`](app/blueprints/auth.py) (~11K), [`app/blueprints/jobs.py`](app/blueprints/jobs.py) (~40K), [`app/blueprints/jobs_api.py`](app/blueprints/jobs_api.py) (~9K)  
> **Метод:** Статический анализ с выборочной верификацией через чтение сервисного слоя и декораторов

---

## 1. [`app/blueprints/auth.py`](app/blueprints/auth.py)

### Найдено проблем: 8

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **HIGH** | Корректность | `NameError` при неудачном `resp.json()`: переменная `err_data` не определена в except-блоке, а используется на строке 244 | [app/blueprints/auth.py:238-244](app/blueprints/auth.py) | Перенести `err_data = resp.json()` перед `try`, либо инициализировать `err_data = None` до try |
| 2 | **MEDIUM** | Безопасность | Пароль валидируется только на `len >= 6`, без требований к сложности (цифры, спецсимволы, регистр) | [app/blueprints/auth.py:147-148](app/blueprints/auth.py) | Добавить проверку: минимум 1 цифра, 1 заглавная, 1 спецсимвол, длина >= 8 |
| 3 | **MEDIUM** | Безопасность | Регистрация использует `postgrest_admin_request` (service_role) для создания профиля и навыков — обход RLS необходим, но операции не атомарны: RPC register_user -> PATCH profile -> цикл POST user_skills. При сбое на PATCH остаётся полу-созданный пользователь | [app/blueprints/auth.py:177-227](app/blueprints/auth.py) | Объединить register_user + profile update в одну RPC-процедуру, либо добавить компенсирующую логику (удаление пользователя при сбое) |
| 4 | **MEDIUM** | Производительность | `login()` использует `_time.sleep()` внутри обработчика запроса — блокирует WSGI-воркер на время backoff (до 4.5 сек при 3 попытках). Потенциальный вектор Slowloris-атаки | [app/blueprints/auth.py:99,107](app/blueprints/auth.py) | Перенести rate-limiting на декоратор `@rate_limit`, убрать sleep из обработчика |
| 5 | **LOW** | Качество | `_generate_jwt()` жёстко задаёт `refresh_token = 'jwt'` — вводит в заблуждение (refresh-токен не является реальным JWT) | [app/blueprints/auth.py:61](app/blueprints/auth.py) | Убрать refresh_token из сессии или хранить реальный refresh-токен, если он поддерживается |
| 6 | **LOW** | Безопасность | `_SQL_INJECTION_PATTERNS` защищает от SQL-ключевых слов в ASCII-фрагментах, но PostgREST уже параметризует запросы. Защита defence-in-depth, но regex хрупкий (например, `\b` в середине строки не сработает) | [app/blueprints/auth.py:25-29](app/blueprints/auth.py) | Оставить как defence-in-depth, но добавить тесты на граничные случаи (Unicode-инъекции, mixed encoding) |
| 7 | **LOW** | Качество | Дублирование валидации: email проверяется и `_EMAIL_RE`, и `_has_sql_injection()`. Для email достаточно regex-валидации | [app/blueprints/auth.py:140-143](app/blueprints/auth.py) | Убрать SQL-injection проверку для email (формат email исключает инъекции) |
| 8 | **LOW** | Качество | Импорт `_uuid` с алиасом — нестандартный стиль, затрудняет чтение | [app/blueprints/auth.py:1](app/blueprints/auth.py) | Импортировать `from uuid import UUID`, использовать `UUID(sid)` |

---

## 2. [`app/blueprints/jobs.py`](app/blueprints/jobs.py)

### Найдено проблем: 15

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **HIGH** | Корректность | `index()` — пагинация сломана: фильтрация по статусу, expires_at, blacklist, навыкам и радиусу выполняется **после** limit/offset в Python, а не в БД. Страница 2 может содержать 0-20 записей вместо ожидаемых 20, часть заданий пропускается | [app/blueprints/jobs.py:126-185](app/blueprints/jobs.py) | Перенести все фильтры в PostgREST-запрос (WHERE-условия). Python-фильтрацию оставить только для георасстояния и навыков, компенсируя offset |
| 2 | **HIGH** | Корректность | `index()` — поиск по навыкам ссылается на `detailed_description`, но поле **не выбрано** в `select=...` (исключено как "тяжёлое"). Поиск по описанию не работает — false negative | [app/blueprints/jobs.py:119,146](app/blueprints/jobs.py) | Либо включить `detailed_description` в select, либо убрать его из поискового выражения на строке 146 |
| 3 | **MEDIUM** | Безопасность | `delete_job()` удаляет уведомления через `message=ilike.*{job_id}*` — поиск подстроки в тексте хрупкий (ложные срабатывания на других job_id с похожими цифрами), нестандартный подход. Комментарий говорит об отсутствии колонки `job_id` в notifications | [app/blueprints/jobs.py:717](app/blueprints/jobs.py) | Добавить колонку `job_id` в таблицу `notifications`, использовать `notifications?job_id=eq.{job_id}` |
| 4 | **MEDIUM** | Корректность | `cancel_job()`: race condition между проверкой accepted-откликов (GET, стр. 554-556) и отменой (PATCH, стр. 565). Между запросами может появиться новый accepted-отклик | [app/blueprints/jobs.py:553-565](app/blueprints/jobs.py) | Заменить на RPC `cancel_job_atomic`, которая проверяет и отменяет в одной транзакции |
| 5 | **MEDIUM** | Корректность | `force-complete` (`/api/jobs/<id>/force-complete`): массовый reject pending (стр. 664-665) и установка completed (стр. 668) — две неатомарные операции. При сбое второй — задание остаётся open с уже отклонёнными откликами | [app/blueprints/jobs.py:663-668](app/blueprints/jobs.py) | Объединить в RPC `force_complete_job` с атомарным выполнением |
| 6 | **MEDIUM** | Корректность | `edit_job()`: проверка `has_accepted` (стр. 774-776) и последующее редактирование (стр. 823) неатомарны — race condition: между проверкой и PATCH может появиться accepted-отклик, редактирование пройдёт, когда не должно | [app/blueprints/jobs.py:774-823](app/blueprints/jobs.py) | Добавить повторную проверку в RPC или использовать оптимистичную блокировку (version-поле) |
| 7 | **MEDIUM** | Производительность | `inject_application_count()` (контекстный процессор) делает HTTP-запрос к PostgREST на **каждый** запрос для работодателей. При 50 одновременных работодателях — 50 лишних запросов/сек | [app/blueprints/jobs.py:81-85](app/blueprints/jobs.py) | Кэшировать в Redis с TTL 30 сек, аналогично проблеме из Stage 1 (#3 в `__init__.py`) |
| 8 | **MEDIUM** | Качество | `my_jobs()` делает два запроса для получения количества откликов: `applications(count)` в основном запросе (стр. 455) + повторный batch-запрос (стр. 467). Один из запросов избыточен | [app/blueprints/jobs.py:455-474](app/blueprints/jobs.py) | Оставить только batch-запрос, убрать `applications(count)` из основного select |
| 9 | **MEDIUM** | Корректность | `my_jobs()` не использует декоратор `@role_required('employer')`, а проверяет роль вручную (стр. 447-449). Непоследовательно с другими эндпоинтами (например, `job_new` использует декоратор) | [app/blueprints/jobs.py:447-449](app/blueprints/jobs.py) | Добавить `@role_required('employer')`, убрать ручную проверку |
| 10 | **MEDIUM** | Производительность | `index()` — `in.()` фильтр для рейтингов (стр. 166): при 100+ employer_ids URL превышает лимит PostgREST (~8KB). Запрос молча обрежется или вернёт ошибку | [app/blueprints/jobs.py:164-166](app/blueprints/jobs.py) | Разбивать на батчи по 50 ID или вынести сортировку по рейтингу в RPC |
| 11 | **LOW** | Качество | `my_jobs_action()` — цикл по job_ids с индивидуальными запросами для duplicate (GET + POST на каждое задание). При 10 заданиях — 20 запросов | [app/blueprints/jobs.py:494-507](app/blueprints/jobs.py) | Заменить на batch-RPC `duplicate_jobs` |
| 12 | **LOW** | Корректность | `add_favorite_job()` и `remove_favorite_job()` не проверяют результат `supabase_request` — при ошибке БД пользователь видит success-flash | [app/blueprints/jobs.py:846,854](app/blueprints/jobs.py) | Добавить проверку `resp.ok`, показывать ошибку при неудаче |
| 13 | **LOW** | Корректность | `add_favorite_job()` не проверяет существование задания перед вставкой в `job_favorites`. Supabase-констрейнт отклонит запись, но ошибка будет 500, а не понятное сообщение | [app/blueprints/jobs.py:846](app/blueprints/jobs.py) | Добавить проверку `jobs?id=eq.{job_id}&select=id` перед вставкой |
| 14 | **LOW** | Безопасность | `cancel_job()` использует `supabase_admin_request` (service_role) для PATCH статуса (стр. 565). Владелец уже проверен через `check_job_owner`, но обход RLS не соответствует паттерну других операций | [app/blueprints/jobs.py:565](app/blueprints/jobs.py) | Использовать `supabase_request` (anon ключ), если RLS-политика разрешает изменение статуса владельцем |
| 15 | **LOW** | Качество | Четыре пустые строки между функциями (стр. 94-96) — нестандартное форматирование | [app/blueprints/jobs.py:94-96](app/blueprints/jobs.py) | Оставить 2 пустые строки по PEP 8 |

---

## 3. [`app/blueprints/jobs_api.py`](app/blueprints/jobs_api.py)

### Найдено проблем: 7

| # | Серьёзность | Категория | Проблема | Строка/фрагмент | Рекомендация |
|---|------------|-----------|----------|-----------------|--------------|
| 1 | **HIGH** | Корректность | `respond_invitation()` — при accept создаёт заявку со статусом `accepted` напрямую (стр. 206-209), **минуя** бизнес-правила `apply_job_atomic` RPC: не проверяются дубликат, чёрный список, статус задания, свободные места. Трудник может быть принят на заполненное задание | [app/blueprints/jobs_api.py:204-210](app/blueprints/jobs_api.py) | Использовать `supabase_rpc('apply_job_atomic', ...)` для создания заявки при принятии приглашения |
| 2 | **MEDIUM** | Корректность | `respond_invitation()` — создание заявки (POST applications, стр. 206) и обновление счётчика `current_workers` (PATCH jobs, стр. 220-223) неатомарны. При сбое PATCH jobs — принятая заявка с неверным счётчиком | [app/blueprints/jobs_api.py:206-223](app/blueprints/jobs_api.py) | Заменить на RPC `accept_invitation_atomic`, объединяющую обе операции в одной транзакции |
| 3 | **MEDIUM** | Корректность | `invite_worker()`: проверка свободных мест (стр. 129) и создание приглашения (стр. 133) неатомарны — race condition: между проверкой и вставкой место может быть занято | [app/blueprints/jobs_api.py:122-138](app/blueprints/jobs_api.py) | Перенести проверку в RPC или использовать `apply_job_atomic` при принятии приглашения (см. #1) |
| 4 | **LOW** | Качество | `api_search_jobs()` импортирует `traceback` внутри функции (стр. 60) — неэффективно, нестандартно | [app/blueprints/jobs_api.py:60](app/blueprints/jobs_api.py) | Перенести `import traceback` на уровень модуля |
| 5 | **LOW** | Корректность | `api_search_workers()` не имеет try/except, в отличие от `api_search_jobs()`. Ошибка в `search_workers()` приведёт к 500 без лога | [app/blueprints/jobs_api.py:85-99](app/blueprints/jobs_api.py) | Добавить try/except с `current_app.logger.error()` и возвратом `jsonify({'error': ...}), 500` |
| 6 | **LOW** | Качество | `list_invitations()` (стр. 155-171) дублирует логику `invitations_page()` из [`jobs.py:730-743`](app/blueprints/jobs.py) — разница только в формате ответа (JSON vs HTML) | [app/blueprints/jobs_api.py:161-170](app/blueprints/jobs_api.py) | Вынести общую логику запроса в `job_service.get_invitations(user_id, role)` |
| 7 | **LOW** | Качество | `invite_worker()` использует `msg.get('message', '')` с `request.get_json(silent=True)` (стр. 132). При ошибке парсинга JSON молча возвращается `{}`, и message теряется | [app/blueprints/jobs_api.py:132](app/blueprints/jobs_api.py) | Добавить валидацию: если Content-Type = application/json, но парсинг не удался — вернуть 400 |

---

## Общая сводка

| Файл | CRITICAL | HIGH | MEDIUM | LOW | Всего |
|------|----------|------|--------|-----|-------|
| [`auth.py`](app/blueprints/auth.py) | 0 | 1 | 3 | 4 | **8** |
| [`jobs.py`](app/blueprints/jobs.py) | 0 | 2 | 8 | 5 | **15** |
| [`jobs_api.py`](app/blueprints/jobs_api.py) | 0 | 1 | 2 | 4 | **7** |
| **ИТОГО** | **0** | **4** | **13** | **13** | **30** |

---

## Топ-10 проблем (все три файла)

| Ранг | Серьёзность | Файл:Строка | Проблема |
|------|------------|-------------|----------|
| 1 | HIGH | [`jobs.py:126`](app/blueprints/jobs.py) | Сломана пагинация: фильтры применяются после limit/offset, страницы неравномерны |
| 2 | HIGH | [`jobs.py:146`](app/blueprints/jobs.py) | Поиск по навыкам ссылается на `detailed_description`, которое не выбрано в select — false negative |
| 3 | HIGH | [`jobs_api.py:206`](app/blueprints/jobs_api.py) | Принятие приглашения создаёт заявку bypass'ом бизнес-правил `apply_job_atomic` |
| 4 | HIGH | [`auth.py:238`](app/blueprints/auth.py) | `NameError` при неудачном `resp.json()` — переменная `err_data` не определена |
| 5 | MEDIUM | [`jobs.py:553`](app/blueprints/jobs.py) | Race condition в `cancel_job()` — проверка accepted-откликов и отмена неатомарны |
| 6 | MEDIUM | [`jobs.py:663`](app/blueprints/jobs.py) | `force-complete` — reject pending и set completed неатомарны |
| 7 | MEDIUM | [`jobs.py:774`](app/blueprints/jobs.py) | `edit_job()` — проверка `has_accepted` и PATCH неатомарны |
| 8 | MEDIUM | [`jobs_api.py:206`](app/blueprints/jobs_api.py) | `respond_invitation` accept: POST applications + PATCH jobs неатомарны |
| 9 | MEDIUM | [`auth.py:177`](app/blueprints/auth.py) | Регистрация неатомарна: RPC -> PATCH -> цикл POST — риск полу-созданного пользователя |
| 10 | MEDIUM | [`jobs.py:717`](app/blueprints/jobs.py) | Удаление уведомлений через `ilike.*job_id*` — хрупкий поиск подстроки |

---

## Общие паттерны проблем (cross-cutting concerns)

### 1. Неатомарные операции (7 проблем)
Наиболее частый паттерн — распределённая бизнес-логика с несколькими последовательными HTTP-запросами к PostgREST без транзакционной защиты:

- [`jobs.py:553-565`](app/blueprints/jobs.py) — cancel_job: проверка accepted + отмена
- [`jobs.py:663-668`](app/blueprints/jobs.py) — force-complete: reject pending + set completed
- [`jobs.py:774-823`](app/blueprints/jobs.py) — edit_job: проверка accepted + PATCH
- [`jobs_api.py:206-223`](app/blueprints/jobs_api.py) — respond_invitation: POST application + PATCH jobs
- [`jobs_api.py:122-138`](app/blueprints/jobs_api.py) — invite_worker: проверка мест + POST invitation
- [`auth.py:177-227`](app/blueprints/auth.py) — register: RPC + PATCH + цикл POST

**Рекомендация:** создать RPC-процедуры для каждой составной операции: `cancel_job_atomic`, `force_complete_job`, `accept_invitation_atomic`, `register_user_full`. В проекте уже есть успешные примеры: `accept_application` (миграция 039), `apply_job_atomic` (миграция 048), `delete_job_cascade` (миграция 039).

### 2. Race conditions (5 проблем)
Тесно связано с #1. Все операции "проверить-и-изменить" (check-then-act) уязвимы к гонкам между GET и PATCH/POST:

- Проверка accepted-откликов перед cancel/edit
- Проверка свободных мест перед invite
- Проверка статуса перед force-complete

**Рекомендация:** использовать атомарные RPC с `SECURITY DEFINER` и проверками внутри транзакции, либо оптимистичные блокировки (version-поле + `UPDATE ... WHERE version = old_version`).

### 3. Разрыв между серверной и БД-пагинацией (1 проблема, но критичная)
[`jobs.py:126-185`](app/blueprints/jobs.py) — фильтрация в Python после SQL-limit/offset нарушает контракт пагинации. Это архитектурная проблема: часть фильтров (статус, expires_at, blacklist, навыки) невозможно выразить в PostgREST-синтаксисе без RPC.

**Рекомендация:** создать RPC `search_jobs_page(filters, page, per_page)`, возвращающую `{jobs: [...], total_count: N}` с отфильтрованными и пагинированными результатами.

### 4. Избыточные запросы к БД (4 проблемы)
- [`jobs.py:81-85`](app/blueprints/jobs.py) — `inject_application_count()` на каждый запрос
- [`jobs.py:455-474`](app/blueprints/jobs.py) — двойной запрос количества откликов в `my_jobs()`
- [`jobs.py:166`](app/blueprints/jobs.py) — `in.()` с потенциально сотнями ID
- [`jobs.py:503-504`](app/blueprints/jobs.py) — цикл GET+POST для duplicate

**Рекомендация:** кэшировать частые запросы (Redis), батчевые операции выполнять через RPC, избегать циклов по ID.

### 5. Непоследовательное использование декораторов vs ручных проверок (2 проблемы)
- [`jobs.py:447-449`](app/blueprints/jobs.py) — `my_jobs()` проверяет роль вручную вместо `@role_required('employer')`
- [`jobs.py:565`](app/blueprints/jobs.py) — `cancel_job()` использует `supabase_admin_request` вместо `supabase_request`

**Рекомендация:** унифицировать: все защищённые эндпоинты — через декораторы, все мутации — через `supabase_request` (anon) если RLS позволяет.

### 6. Отсутствие обработки ошибок в избранном (2 проблемы)
[`jobs.py:846,854`](app/blueprints/jobs.py) — `add_favorite_job()` и `remove_favorite_job()` не проверяют `resp.ok`, всегда показывают success.

**Рекомендация:** добавить проверку результата, логировать ошибки.

---

## Рекомендация

**NEEDS CHANGES** — 4 HIGH и 13 MEDIUM проблем требуют исправления. Ключевые приоритеты:

1. **Сломана пагинация** [`jobs.py:126`](app/blueprints/jobs.py) — пользователи видят неполные/пропущенные результаты поиска
2. **Обход бизнес-правил** [`jobs_api.py:206`](app/blueprints/jobs_api.py) — принятие приглашения bypass'ит проверки `apply_job_atomic`
3. **Неатомарные операции** — 7 составных операций без транзакционной защиты, потенциально несогласованное состояние БД
4. **`NameError` в регистрации** [`auth.py:238`](app/blueprints/auth.py) — баг, ломающий обработку ошибок при конфликте email

Позитивный момент: проект уже использует RPC для критических операций (`accept_application`, `apply_job_atomic`, `delete_job_cascade`). Распространение этого паттерна на остальные составные операции решит большинство проблем с атомарностью и race conditions.
