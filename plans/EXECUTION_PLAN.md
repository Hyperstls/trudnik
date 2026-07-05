# EXECUTION_PLAN.md — Рефакторинг trudnik (подготовка к масштабированию без монетизации)

> **Назначение документа.** Это пошаговое, исполнимое задание для следующего агента-разработчика. Документ фиксирует диагностику текущего состояния приложения trudnik, фильтрует рекомендации из архива `Plan/` по отношению к реальному коду, и описывает конкретные изменения, которые разрешено вносить **без изменения бизнес-логики бесплатной версии и без внедрения платежей**.
>
> **Главное правило.** Любая рекомендация, затрагивающая платежи, подписки, тарифы, KKT, ЭДО, фискализацию, биллинговые провайдеры (YooKassa, CloudPayments и т. п.) — **откладывается**. В код добавляются только абстрактные интерфейсы-заглушки, которые в будущем позволят подключить биллинг без переписывания ядра.

---

## 0. Жёсткие ограничения (читать перед любым действием)

| Запрет | Пояснение |
|---|---|
| **Не читать и не использовать** папки `archive/`, `trash/`, `Promts/` внутри `trudnik/` | В них лежат устаревшие дубликаты кода, старые тесты и промты; их трогать нельзя. |
| **Не внедрять монетизацию** | Никаких реальных вызовов платёжных провайдеров, никаких `@requires_plan`, никаких CHECK-ограничений на тарифы, изменяющих текущее поведение. |
| **Не менять UI без необходимости** | Допускается только правка шаблонов для устранения XSS (Jinja2 autoescape / `\|e` / `\|tojson`), добавление `loading="lazy"` к картинкам, и исправление бага logout в Service Worker. Дизайн, копейки, раскладка — неприкосновенны. |
| **Не удалять и не переименовывать сущности БД** | Миграции — только аддитивные (`CREATE INDEX`, `CREATE FUNCTION`, `ALTER TABLE ... ADD COLUMN` с `DEFAULT NULL`). Запрещены `DROP COLUMN`, `RENAME`, изменение `CHECK`-ограничений на `tariff`/`is_paid`. |
| **Не чинить «битые хуки» биллинга молча** | Несоответствия вроде `tariff='standard'` vs CHECK `('basic','pro','business')`, отсутствие записи в `employer_subscriptions` при регистрации работодателя, отсутствие `is_paid` в `job_new` — **НЕ исправлять**. Они задокументированы в разделе 4 как «несоответствия рекомендации и реальности» и помечены как будущая зона ответственности биллинг-команды. |
| **Все скрипты рефакторинга сохранять** | В `/home/z/my-project/scripts/` (или в репозитории trudnik в `scripts/refactor/`). Не запускать длинные скрипты inline. |
| **Обратная совместимость сессий** | После изменений залогиненный пользователь не должен разлогиниваться. Структура Flask session и JWT claims должна остаться совместимой. |

---

## 1. Диагностика (ШАГ 1 — без изменений)

### 1.1 Стек технологий

| Слой | Технология | Версия | Источник |
|---|---|---|---|
| Backend-фреймворк | Flask | 3.1.3 | `requirements.txt:1` |
| ASGI-сервер | Uvicorn | 0.49.0 | `requirements.txt:7`, `supervisord.conf:9` |
| WSGI-обёртка | `a2wsgi.WSGIMiddleware` | — | `asgi.py:10` |
| База данных | PostgreSQL 15 + PostGIS | — | `docker-compose.yml:48-49` |
| DB-доступ | **PostgREST v12.2.3** (HTTP API, без ORM) | — | `docker-compose.yml:48-49`, `app/utils/postgrest_client.py` |
| Кэш / брокер | Redis 7-alpine | — | `docker-compose.yml:5` |
| Фоновые задачи | Celery | 5.6.3 | `requirements.txt:9`, `app/tasks/` |
| WebSocket-сервер | FastAPI + `redis.asyncio` | 0.137.1 | `websocket_server/main.py` |
| Аутентификация | JWT (PyJWT 2.13.0, HS256, `PGRST_JWT_SECRET`) + bcrypt 5.0.0 (12 rounds) | — | `app/utils/auth.py:20,100` |
| Email | smtplib (stdlib) + Jinja2-шаблоны | — | `app/services/email_service.py` |
| Push | pywebpush 2.3.0 + VAPID | — | `app/services/push_service.py` |
| Frontend | Jinja2 3.1.6 + Tailwind CSS (скомпилированный) + ванильный JS + PWA (Service Worker) | — | `templates/`, `static/` |
| Деплой | Docker + supervisord (Amvera) | — | `Dockerfile`, `supervisord.conf`, `amvera.yaml` |
| Python | 3.12-slim | — | `Dockerfile:1` |

### 1.2 Ключевые модули

**Готовая Service Layer** (но используется непоследовательно):
- `app/services/job_service.py` — поиск/фильтрация вакансий, проверка ownership/visibility.
- `app/services/application_service.py` — withdraw заявки (с fallback).
- `app/services/notification_service.py` — мультиканальные уведомления (DB + Redis Pub/Sub + Celery).
- `app/services/email_service.py` — SMTP-клиент с пулом и дневными лимитами.
- `app/services/push_service.py` — Web Push (VAPID).
- `app/services/storage_service.py` — локальная файловая загрузка (замена Supabase Storage).
- `app/services/ratings_service.py` — пересчёт агрегированного рейтинга.
- `app/services/invitation_service.py` — список приглашений.
- `app/services/redis_publisher.py` — синхронный Redis Pub/Sub.
- `app/services/payment_service.py` — **dead code** (см. §1.4).

**14 Blueprint'ов** в `app/blueprints/`: `auth`, `profile`, `jobs`, `jobs_api`, `applications`, `chat`, `favorites`, `blacklist`, `notifications`, `admin`, `ratings`, `employers`, `seo`. Бизнес-логика частично дублируется между blueprint'ами и services.

**Utils** (`app/utils/`):
- `postgrest_client.py` (671 строка) — ядро DB-доступа, circuit breaker, mock-поддержка.
- `auth.py` — JWT + bcrypt.
- `security.py` — `sanitize_postgrest`, `validate_uuid`, эвристика SQL-инъекций.
- `redis_client.py` — ленивый Redis-клиент + lockout/blacklist.
- `rate_limit.py` — **устаревший** in-memory rate-limit (заменён на `app/decorators.py:rate_limit`, но всё ещё реэкспортируется).
- `db_pool.py` — пул psycopg2 для emergency-эндпоинтов.
- `helpers.py`, `formatting.py`, `geo.py`, `business.py`, `validators.py`.

**Celery-задачи** (`app/tasks/`): `email_tasks`, `push_tasks`, `maintenance_tasks`. Beat-расписание содержит 3 периодические задачи (`celery_app.py:81-103`).

### 1.3 Архитектурные слабые места (узкие места)

| ID | Тип | Где | Описание |
|---|---|---|---|
| BN-1 | Производительность | `app/blueprints/admin.py:47-103` | Dashboard делает 8 последовательных `count=exact` запросов к PostgREST за 500–800 мс. |
| BN-2 | Производительность | `app/decorators.py:67-88` | `role_required` делает HTTP-запрос к PostgREST на каждый защищённый запрос (+50–150 мс). |
| BN-3 | N+1 | `app/services/job_service.py:45-65` | `enrich_job_with_references` делает 2 доп. PostgREST-запроса на каждую вакансию (work_type, preferred_religion). |
| BN-4 | N+1 | `app/blueprints/jobs.py:353-415` | `job_detail` делает 5+ последовательных запросов (job, employer, applications count, own app, favorite). |
| BN-5 | N+1 | `app/blueprints/jobs.py:824-864` | `delete_job` делает 7 последовательных DELETE вместо одной RPC-функции. |
| BN-6 | Отсутствие пагинации | `app/blueprints/chat.py:58-66` | `chat` грузит ВСЕ сообщения без лимита. |
| BN-7 | Блокировка импорта | `app/__init__.py:72-110` | `_wait_for_postgrest` блокирует запуск на 30 с; `app = create_app()` на уровне модуля ломает `gunicorn --preload`. |
| BN-8 | In-memory cache | `app/utils/postgrest_client.py:249-275` | `cache_for` хранит данные в closure-local dict — бесполезен под gunicorn (у каждого воркера свой кэш), без eviction (утечка памяти). |
| BN-9 | Thread-safety | `app/utils/postgrest_client.py:232-242` | Глобальный `requests.Session()` шарится между потоками gunicorn (race в пуле соединений). |
| BN-10 | Thread-safety | `app/services/email_service.py:75-165` | SMTP-пул не thread-safe; `starttls()`/`login()` без timeout. |
| BN-11 | JWT per request | `app/utils/postgrest_client.py:319-339` | На каждый `postgrest_request` подписывается новый JWT (pyjwt.encode) + делается `SETEX` в Redis. |
| BN-12 | Rate-limit in-memory | `app/utils/rate_limit.py` | Словарь в памяти; под N gunicorn-воркерами каждый пользователь имеет N×limit. |
| BN-13 | Blocking I/O в обработчике | `app/blueprints/admin.py:167-172` | `subprocess.check_output(['git','log',...])` на каждый `/admin` запрос. |
| BN-14 | Context processors | `app/context_processors.py:150-266` | На каждый рендер страницы делаются 3+ PostgREST-запроса (unread, invitations, subscription). |
| BN-15 | Service Worker кэширует HTML/API | `static/sw.js:71-82, 122-132` | Кэширует HTML и API-ответы — утечка аутентифицированного контента анонимным пользователям. |

### 1.4 Уязвимости безопасности (критичные)

| ID | Серьёзность | Файл:строка | Описание |
|---|---|---|---|
| SEC-1 | **CRITICAL** | `app/utils/auth.py:96-99` | Логируется префикс JWT-секрета (8 символов) на уровне **INFO** при каждой генерации токена (т. е. на каждый PostgREST-запрос). |
| SEC-2 | **CRITICAL** | `app/config.py:36-37` | Логируется префикс `PGRST_JWT_SECRET` (16 символов) на уровне DEBUG. |
| SEC-3 | **CRITICAL** | `app/services/payment_service.py` (весь файл) | **Dead code.** `verify_webhook` использует `hexdigest()` вместо ожидаемого YooKassa base64; в dev-режиме возвращает `True` без проверки; `process_payment` не имеет authz. Ни один метод не вызывается из blueprint'ов. См. §4. |
| SEC-4 | **HIGH** | `websocket_server/auth.py:17` | Хардкод-фолбэк `"dev-secret-change-me"` для `SECRET_KEY`. Если env не задан, WS-аутентификация подписывает/проверяет токены этим ключом. |
| SEC-5 | **HIGH** | `app/services/email_service.py:442` | Хардкод-фолбэк `"fallback-secret-key"` для HMAC unsubscribe-токенов. |
| SEC-6 | **HIGH** | `app/services/email_service.py:114` | **Баг:** `_time_module.timedelta(days=1)` — у модуля `time` нет `timedelta`. `AttributeError` при первом инкременте дневного лимита. |
| SEC-7 | **HIGH** | `app/blueprints/auth.py:551-562` | **Баг:** `from app.services.email_service import send_email` — `send_email` это метод класса `EmailService`, не модульная функция. Сигнатура вызова тоже неверная (`body=` вместо `text_body=`, `html_body=`). Password-reset email flow сломан. |
| SEC-8 | **HIGH** | `app/decorators.py:127-132` | `admin_required` при ошибке БД падает в `session.get('role')` — session-tampering bypass, когда PostgREST недоступен. |
| SEC-9 | **HIGH** | `app/__init__.py:368-372` | `/uploads/<path:filename>` отдаёт файлы без auth — verification-документы работодателей публично читаемы, если URL утёк. |
| SEC-10 | **HIGH** | `app/blueprints/applications.py:81-86, 281-296` | `threading.Thread(daemon=True)` для уведомлений — теряются при shutdown воркера. Должно быть через Celery. |
| SEC-11 | **HIGH** | `app/__init__.py:199-237` | CSRF-bypass для admin-API через `X-Admin-Token` падает в `SECRET_KEY`, когда `ADMIN_API_TOKEN` не задан; `hmac.compare_digest('', '') == True` — оба пустые → проходит. |
| SEC-12 | **HIGH** | `app/blueprints/admin.py:745-824` | `/api/fix-permissions` выполняет прямые `GRANT` SQL, защищён только `X-Admin-Token`, без rate-limit и без audit-log. |
| SEC-13 | **HIGH** | `websocket_server/main.py:41-42, 200-206` | Wildcard CORS (`*`) с `allow_credentials=True` на WebSocket. |
| SEC-14 | **HIGH** | `websocket_server/main.py:54, 213-239` | WS-JWT передаётся в URL `?token=` (логируется nginx) + single-connection eviction (второй логин молча убивает первую сессию). |
| SEC-15 | **HIGH** | `app/context_processors.py:121-147` vs `websocket_server/auth.py:17-35` | WS-JWT подписывается `SECRET_KEY`, проверяется `PGRST_JWT_SECRET`; claim называется `user_id` в одном месте и `sub` в другом. WS-аутентификация не работает. |
| SEC-16 | **HIGH** | `app/context_processors.py:134-142`, `templates/base.html:555-560` | 7-дневный WS-JWT инжектируется в `window.TRUDNIK_CONFIG` на каждой странице — любой XSS утаскивает долгоживущий токен. |
| SEC-17 | **HIGH** | `templates/job_detail.html:522`, `templates/base.html:738, 964-966`, `templates/admin.html:510-513`, `templates/_filter_skills.html:143-145` | Stored XSS: `raterName` без `\|e`; flash-сообщения рендерятся как raw; `value="${s.name}"` без экранирования. |
| SEC-18 | **HIGH** | `app/blueprints/applications.py:18, 21` | `/apply/<job_id>` принимает GET — CSRF-вектор и случайные переходы роботов. То же в `jobs.py:672, 726, 824` для `/cancel-job`, `/restore-job`, `/delete-job`. |
| SEC-19 | **HIGH** | `app/blueprints/auth.py:536` | Email вставляется в PostgREST URL `profiles?email=eq.{email}` только после regex-проверки; специальные символы PostgREST (`,`, `&`, `:`) не экранируются. |
| SEC-20 | **HIGH** | `app/blueprints/admin.py:106-116` | Админ-поиск использует `ilike.*...*` — pattern-injection через `|`, `(`, `)` (OR-conditions). |
| SEC-21 | **MEDIUM** | `app/blueprints/admin.py:119` | `select=*` на `profiles` выгружает `password_hash`, `notification_prefs`, `bio` в админку. |
| SEC-22 | **MEDIUM** | Несколько (`favorites.py:53`, `blacklist.py:53,57`, `employers.py:175,177`, `jobs.py:1006,1016`) | Open redirect через `request.referrer`. |
| SEC-23 | **MEDIUM** | `app/blueprints/admin.py:862-998` | `/api/reset-users` создаёт тестовых пользователей с паролем `changeme123` без env-gate. |
| SEC-24 | **MEDIUM** | `migrations/067_bootstrap_amvera.sql:2314-2323` | Хардкод admin email. |
| SEC-25 | **MEDIUM** | `app/blueprints/auth.py:195-213` | Lockout только по email (attacker можетenumerate); `/password-reset` не имеет IP rate-limit. |
| SEC-26 | **MEDIUM** | `app/blueprints/applications.py:413-417` | `worker_contacts` отдаёт email работника работодателю безусловно. |
| SEC-27 | **MEDIUM** | `app/blueprints/profile.py:253-289` | `verify_employer` без role-check и без проверки `verification_status`. |
| SEC-28 | **MEDIUM** | `app/blueprints/profile.py:141-169` | `delete_photo` без ownership-check. |
| SEC-29 | **MEDIUM** | `app/blueprints/profile.py:172-197` | `delete_account` без подтверждения паролем. |
| SEC-30 | **MEDIUM** | `app/blueprints/jobs.py:432-565` | Декоратор-порядок: `@login_required` → `@role_required` → `@rate_limit`. Python применяет снизу вверх, поэтому `role_required` (с PostgREST-запросом) срабатывает до `rate_limit` — DoS-вектор. |
| SEC-31 | **MEDIUM** | Десятки routes (см. R-33 в §2) | Отсутствует `@validate_uuid` на UUID path/query параметрах (jobs_api, applications, admin bulk-delete, favorites, blacklist, employers, notifications). |
| SEC-32 | **MEDIUM** | `app/blueprints/jobs.py:854-858`, `app/blueprints/notifications.py:70-78` | DELETE уведомлений по `message=ilike.*{job_id}*` — паттерн-ориентированное удаление (хрупко, race-prone). |

---

## 2. Фильтрация рекомендаций из архива Plan (ШАГ 2)

### 2.1 Категория A — ПРИМЕНИТЬ СЕЙЧАС

125 рекомендаций из архива `Plan/` сопоставлены с реальным кодом. В Категорию A включены **те, которые улучшают безопасность/производительность/читаемость или добавляют абстракции без изменения бизнес-логики бесплатной версии**. Полный перечень приведён в §3 (исполнимый план) — ниже сводка по группам.

**A. Безопасность (критично):**
- R-1, R-2 — ротация секретов + убрать логирование префикса JWT (соответствует SEC-1, SEC-2).
- R-3, R-11, R-20 — отделить `ADMIN_API_TOKEN` от `SECRET_KEY`; запретить empty-token bypass; `jti`-блеклист в Redis при refresh.
- R-9, R-36, R-40 — `@role_required('worker')` на `apply_job`; запретить GET на мутирующих роутах; переставить порядок декораторов.
- R-16, R-17, R-18, R-19 — WebSocket: убрать wildcard CORS, передавать JWT не в URL, унифицировать секрет + claim name, сократить TTL WS-JWT до 5–15 минут.
- R-23, R-25 — санитизация email перед PostgREST URL; ограничить charset админ-поиска.
- R-27, R-28 — XSS-исправления в шаблонах; Jinja2 `autoescape=True` для email.
- R-30 — path-traversal в `/uploads/`, whitelist расширений, MIME-сниффинг.
- R-31, R-32, R-33 — валидация длины полей профиля; UUID + length-check в `chat.send_message`; `@validate_uuid` на десятках роутов.
- R-35 — IDOR-аудит: ownership-чеки на notifications, push-subscriptions, favorites, blacklist, `public_profile`.
- R-37, R-38 — закрыть anonymous-доступ к `/health/postgrest`, `/health/circuit-breaker`, VAPID, `/api/skills`, `/api/religions`, `/api/search_*`, ratings.
- R-41 — аудит-лог должен писать `user_id` администратора (не `None`); покрывать bulk-actions.
- R-10 — logout должен блэклистить `jti` + чистить SW-кэш.
- R-13 — идентичные сообщения об ошибках login; IP rate-limit на password-reset.
- R-15 — unificate lockout между direct-SQL и PostgREST login fallback.

**B. Производительность:**
- R-42 — заменить 8 `count=exact` запросов в админке на одну RPC `get_admin_stats()` (см. §3.5).
- R-43 — кэшировать `session['role']` с revalidation каждые 5 минут вместо запроса на каждый реквест.
- R-44 — агрегация рейтинга одним PostgREST-запросом.
- R-45, R-46 — использовать embedded resources PostgREST (`?select=*,employer:profiles(*),photos:job_photos(*)`) для `job_detail` и `enrich_job_with_references`.
- R-47 — пагинация на `my_applications`, `workers`, `index.html` (cursor-based, не OFFSET).
- R-48 — батчить context processors в один Redis-cached счётчик с инвалидацией на мутации.
- R-49 — Redis-backed `cache_for` с LRU-eviction.
- R-50 — `threading.local()` для `requests.Session`; per-process SMTP; не запускать `_check_postgrest_health` под Lock.
- R-51 — кэшировать JWT в session с TTL 4 минуты (token exp = 5 мин).
- R-52 — различать 5xx (server) и 4xx (client) в CircuitBreaker; `tenacity` для ретраев.
- R-53 — Redis sliding-window rate-limit.
- R-54 — убрать `_wait_for_postgrest` из импорта; lazy-init; убрать `app = create_app()` на уровне модуля.
- R-55 — аддитивные индексы (без удаления полей).
- R-56 — статике дать `Cache-Control: max-age=31536000, immutable` с fingerprint; CSP-nonce кэшировать per session.
- R-57 — Service Worker: не кэшировать HTML/API; починить рекурсивный `/offline?_sw_ping=`.
- R-7 — кэшировать git-версию на старте приложения вместо `subprocess` на каждый `/admin`.

**C. Архитектура / рефакторинг (6-фазная дорожная карта из аудита):**
- R-71 / Phase 0 — infrastructure cleanup: вынести `app/cache.py`, убрать global `app = create_app()`, разорвать круговые импорты.
- R-72 / Phase 1 — иерархия исключений `DomainError`/`InfrastructureError` + централизованные error handlers; заменить 50+ bare `except Exception`.
- R-73 / Phase 2 — Repository pattern (`app/repositories/`) + `get_admin_stats()` RPC; постепенно мигрировать ~80 `postgrest_request` call sites.
- R-74 / Phase 3 — Use Cases (`app/use_cases/`) + Pydantic Commands; убрать `threading.Thread`; удалить TOCTOU fallback paths.
- R-75 / Phase 4 — Redis-backed `cache_for` + `ConnectionRegistry` для multi-replica WebSocket.
- R-76 / Phase 5 — DI-контейнер (`app/container.py`) + `Config` dataclass + `from_env()` factory.
- R-77 — декомпозиция `app/utils/__init__.py` god-module.
- R-78 — расширить Celery на все async-операции.
- R-79 — Pydantic 2 для Command-объектов (Must); Marshmallow 4 для валидации (Should); **НЕ внедрять SQLAlchemy 2** (PostgREST покрывает 95%).
- R-80 — observability: structlog, OpenTelemetry, Prometheus `/metrics`, Sentry.
- R-81 — hard-fail в проде при отсутствии Redis; явно гейтить test/mock code path.
- R-63 — заменить swallowed exceptions на typed errors (связано с R-72).
- R-66 — починить notification service (title column, UUID types, Celery cleanup, NOTIFICATION_TYPES).
- R-67, R-68 — рефакторить `my_jobs_action` и `api_batch_applications` — вынести бизнес-логику в Use Cases.
- R-69 — добавить ownership-чеки для `delete_photo`, password confirmation для `delete_account`, role-check для `verify_employer`.
- R-70 — кастомные страницы ошибок + graceful degradation.
- R-64 — field-specific error messages в `job_new` (не показывать `resp.text`).

**D. Тестирование (параллельно с фазами):**
- R-86 — 4-слойная пирамида: Unit ~70% / Integration ~25% / E2E ~5%; цель ≥70% coverage.
- R-87 — unit-тесты для каждого сервиса и Use Case (`test_payment_service.py`, `test_storage_service.py`, `test_application_service.py`, `test_job_service.py`, `test_circuit_breaker.py`, `test_postgrest_client.py`, `test_context_processors.py`, `test_maintenance_tasks.py`).
- R-88 — API contract-тесты (`schemathesis`/OpenAPI) + integration-тесты на все ~70 роутов.
- R-89 — Playwright E2E (Page Object Model).
- R-92 — Lighthouse CI + k6 load tests + `EXPLAIN ANALYZE` на top-10 запросов.
- R-93 — OWASP ZAP, `pip-audit`, `npm audit`, Trivy/Grype Docker scan, SAST (Bandit/Semgrep).
- R-94 — GitHub Actions CI/CD: lint + test + build + security; staging auto-deploy; manual prod approval; reversible migration check.

**E. Observability / DevOps:**
- R-105 — TLS/HTTPS hardening + security headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).
- R-106 — container hardening (non-root, read-only FS, multi-stage build, image scanning).
- R-104 — incident response plan + `.well-known/security.txt`.
- R-103 — backup & DR strategy (daily `pg_dump`, retention 7/4/12, quarterly restore test).

### 2.2 Категория B — ОТЛОЖИТЬ (биллинг, платежи, тарифы, KKT, ЭДО)

Эти элементы **НЕ выполняются** в текущем плане. Однако в код добавляются **только абстрактные интерфейсы-заглушки** (см. §3.7), которые в будущем позволят подключить биллинг без изменения основной логики.

| ID | Описание | Зачем отложить |
|---|---|---|
| R-65 | Исправление `payment_service.verify_webhook` (`hexdigest` → base64), `process_payment` authz, `create_payment` return_url validation | Реальный платежный провайдер будет выбран позже; исправлять логику сейчас — переписывать потом. **Однако:** в §3.7 добавляется абстрактный `PaymentGateway` interface, чтобы будущая реализация не трогала ядро. |
| R-83 | Распространение `tariff`/`is_paid`/`promoted_until`/`is_promoted` через create/edit/copy/duplicate flows | Это сама логика монетизации — откладывается до биллинг-спринта. **Однако:** несоответствия задокументированы в §4. |
| R-84 | Гейтинг `worker_contacts` / `employer_detail` / `public_profile` по подписке | Связано с тарифами; откладывается. |
| R-98 | 54-ФЗ KKT (АТОЛ Онлайн / Эвотор) | Только после выбора биллинг-модели. |
| R-102 | Публичная оферта для платных услуг | Только после запуска монетизации. |
| R-120 | Feature flags с plan-based segments (`@requires_plan`) | Откладывается; **но** базовый feature-flag интерфейс добавляется в §3.7 как абстракция. |
| R-121 | Vendor risk registry (включая будущего платёжного провайдера) | Документация; может быть подготовлена, но без интеграции. |
| R-123 | Subscription/tariff model (`plans`, `subscriptions`, `transactions`, `invoices`) | Полная откладка. |
| R-124 | Payment provider integration (YooKassa/CloudPayments/Tinkoff/Robokassa), webhooks, idempotency, SBP, auto-renew, refunds, promocodes | Полная откладка. **Однако:** `PaymentGateway` interface в §3.7 подготовит почву. |
| R-125 | Financial reporting, MRR/churn/LTV/CAC, B2B invoicing (УПД/ЭДО) | Полная откладка. |
| R-62 (частично) | `email_service._check_daily_limit` race-condition | Атомарный `INCR` в Redis можно сделать сейчас (не биллинг), но если лимит email-ов станет платным — координировать с биллингом. |

### 2.3 Категория V — ОТКЛОНИТЬ

| ID | Причина отклонения |
|---|---|
| R-21 (частично: WebAuthn для админов) | Слишком тяжёлая инфраструктура для текущей стадии; TOTP 2FA опционально можно добавить, но WebAuthn — оверкилл. |
| R-22 (полный Redis-session с idle/absolute timeouts, device-list, new-device email) | Изменит UX текущих пользователей (выгонит их из сессий). Только после отдельного обсуждения. |
| R-39 (3 admin roles: super_admin/moderator/editor + IP-whitelist + 15-min idle) | Полная перестройка admin-RBAC; текущий одиночный `admin` достаточно для бесплатной версии. |
| R-97 (полная 152-ФЗ compliance: public Privacy Policy, consent checkbox, data-deletion by request, Roskomnadzor notification, data portability export) | Юридическая работа; вне рамок технического рефакторинга. **Однако:** технические предпосылки (audit log, soft-delete vs hard-delete) готовятся в §3. |
| R-99 (TK RF compliance — религиозная специфика трудоустройства) | Юридическая работа. |
| R-100 (GDPR compliance + DSAR workflow) | Только если планируются EU-пользователи. |
| R-107 (полный design system + Storybook) | UI-изменения запрещены ограничениями. |
| R-109 (полный frontend perf: bundle budgets, image optimization, fonts) | UI-изменения запрещены; допускается только `loading="lazy"` и cache-headers. |
| R-110 (PWA rewrite) | UI-изменения запрещены; только bugfix'ы SW (R-57). |
| R-111 (WCAG 2.1 AA full audit + elderly UX) | UI-изменения запрещены. |
| R-113 (admin panel UX deep-dive) | UI-изменения запрещены. |
| R-117 (full-text search via `tsvector` + GIN) | Большая миграция; может быть добавлена как аддитивный индекс, но не приоритет. |
| R-119 (calendar & interview scheduling + video interview) | Новая фича; вне рамок рефакторинга. |
| R-122 (AI/ML bias audit) | Нет matching-алгоритма в коде. |
| R-98 (KKT) | Биллинг. |
| Любая рекомендация, требующая `DROP COLUMN` / `RENAME` / изменения `CHECK`-ограничений | Нарушает обратную совместимость с БД. |

---

## 3. План выполнения (ШАГ 3 — исполнимый)

### Порядок выполнения (согласно требованиям задания)

1. **Фаза 0** — Утилиты и хелперы (инфраструктура).
2. **Фаза 1** — Критичные исправления безопасности (hot-fixes).
3. **Фаза 2** — Ядро бизнес-логики (services + repositories + use cases).
4. **Фаза 3** — API и роуты (blueprints).
5. **Фаза 4** — Инфраструктура и наблюдаемость (Celery, logging, metrics).
6. **Фаза 5** — Заглушки для будущего биллинга (interfaces, без реализации).
7. **Фаза 6** — Тесты.

Каждая задача имеет формат:
- **Task ID** (для логирования в `worklog.md`).
- **Что меняется** (файл, функция, класс).
- **Почему** (ссылка на проблему из §1.3 / §1.4 или на R-ID из §2).
- **Как** (псевдокод / описание изменений).
- **Что проверять** (acceptance criteria).

---

### Фаза 0 — Утилиты и хелперы (инфраструктура)

#### Task 0.1 — Вынести Redis-кэш-хелперы в `app/cache.py`
- **Task ID:** `0.1`
- **Что меняется:** Новый файл `app/cache.py`. Удаление `_redis_cache_get/_set/_delete` из `app/__init__.py:21-69` и `app/context_processors.py:70-118`. Замена импортов в `app/services/notification_service.py:154-155, 219-238, 326-336`, `app/blueprints/jobs.py:79` на `from app.cache import redis_cache_get, redis_cache_set, redis_cache_delete`.
- **Почему:** BN-7, R-71, R-77. Дублирование кода; круговые импорты; `app = create_app()` на уровне модуля блокирует `gunicorn --preload`.
- **Как:**
  ```python
  # app/cache.py
  from app.utils.redis_client import get_redis_client
  import json, logging
  _logger = logging.getLogger(__name__)

  def redis_cache_get(key: str, default=None):
      try:
          client = get_redis_client()
          if not client:
              return default
          raw = client.get(key)
          return json.loads(raw) if raw else default
      except Exception as e:
          _logger.warning("redis_cache_get failed: %s", e)
          return default

  def redis_cache_set(key: str, value, ttl: int = 300) -> None:
      try:
          client = get_redis_client()
          if not client:
              return
          client.setex(key, ttl, json.dumps(value, default=str))
      except Exception as e:
          _logger.warning("redis_cache_set failed: %s", e)

  def redis_cache_delete(*keys: str) -> None:
      try:
          client = get_redis_client()
          if not client:
              return
          client.delete(*keys)
      except Exception as e:
          _logger.warning("redis_cache_delete failed: %s", e)

  # Backward-compat aliases (НЕ удалять до конца миграции)
  _redis_cache_get = redis_cache_get
  _redis_cache_set = redis_cache_set
  _redis_cache_delete = redis_cache_delete
  ```
  В `app/__init__.py` оставить thin re-export `from app.cache import _redis_cache_get, _redis_cache_set, _redis_cache_delete` на 2 спринта для обратной совместимости с внешними импортами.
- **Что проверять:**
  - `python -c "from app.cache import redis_cache_get, redis_cache_set, redis_cache_delete"` работает.
  - `pytest tests/test_notification_service.py` проходит (кэш-моки остаются совместимы).
  - `gunicorn --preload app:create_app` запускается без ImportError.

#### Task 0.2 — Убрать `app = create_app()` с уровня модуля
- **Task ID:** `0.2`
- **Что меняется:** `app/__init__.py:513` — удалить строку `app = create_app()`. Обновить `app.py:6-9` и `asgi.py:10` явно вызывать `create_app()`.
- **Почему:** BN-7, R-54, R-71. Глобальный `app` создаётся при импорте → блокирует `gunicorn --preload`, усложняет тесты.
- **Как:**
  ```python
  # app/__init__.py — конец файла:
  # УДАЛИТЬ:
  # app = create_app()
  # if __name__ == '__main__':
  #     app.run(...)

  # app.py (полная замена):
  from app import create_app
  app = create_app()
  if __name__ == '__main__':
      import os
      port = int(os.environ.get('PORT', 5000))
      app.run(host='0.0.0.0', port=port, debug=False)

  # asgi.py — оставить как есть, но убедиться что create_app() вызывается один раз:
  # app = create_app()  ← уже так
  ```
- **Что проверять:**
  - `gunicorn --preload -w 4 'app:create_app()'` запускается.
  - `pytest` collect-time < 2 с.
  - `supervisord` поднимает uvicorn без изменений.

#### Task 0.3 — Убрать `_wait_for_postgrest` из импорта, сделать lazy
- **Task ID:** `0.3`
- **Что меняется:** `app/__init__.py:72-110, 145-147`. Перенести вызов `_wait_for_postgrest` из `create_app()` в `before_first_request`-хук (или в health-check с fail-fast при первом запросе).
- **Почему:** BN-7, R-54. Блокировка импорта на 30 с; race-condition с Celery.
- **Как:**
  ```python
  # В create_app() заменить:
  #   _wait_for_postgrest()
  # на:
  app._postgrest_ready = False

  @app.before_request
  def _lazy_postgrest_check():
      if not app._postgrest_ready:
          from app.utils.postgrest_client import is_circuit_open
          if is_circuit_open():
              app.logger.warning("PostgREST unavailable, serving 503")
              return "Service temporarily unavailable", 503
          app._postgrest_ready = True
  ```
- **Что проверять:**
  - `import app` не делает HTTP-запросов.
  - При первом запросе, если PostgREST недоступен — 503 вместо hang.
  - Celery не блокируется на старте.

#### Task 0.4 — Удалить мёртвый `import subprocess` и неиспользуемые модули
- **Task ID:** `0.4`
- **Что меняется:**
  - `app/__init__.py:1` — убрать `import subprocess`.
  - Решить, какая из двух `rate_limit` реализаций канонична. Рекомендация: оставить `app/decorators.py:rate_limit` (Redis-based), удалить `app/utils/rate_limit.py`. В `app/utils/__init__.py:133` убрать реэкспорт in-memory версии, добавить `from app.decorators import rate_limit` для обратной совместимости.
  - `app/utils/validators.py:_SQL_INJECTION_PATTERNS` — удалить legacy-копию (каноничная в `app/utils/security.py:101`).
  - `app/blueprints/auth.py:29-33` — удалить локальную копию `_SQL_INJECTION_PATTERNS`.
  - `app/utils/logging_config.py` — либо подключить `setup_json_logging` в `create_app` (Фаза 4), либо удалить файл. В рамках Фазы 0 — оставить как есть, использовать в Фазе 4.
- **Почему:** R-77. God-module `app/utils/__init__.py` экспортирует ~40 функций; устаревшие дубликаты вводят в заблуждение.
- **Как:** Поочерёдно удалить символы, запустить `pytest tests/test_architecture.py tests/test_utils_unit.py` после каждого удаления.
- **Что проверять:**
  - `pytest tests/` проходит.
  - `grep -r "from app.utils import rate_limit" app/` возвращает 0 строк (все импорты переехали на `from app.decorators import rate_limit`).

#### Task 0.5 — Декомпозировать `app/utils/__init__.py`
- **Task ID:** `0.5`
- **Что меняется:** `app/utils/__init__.py` (196 строк) — оставить только thin re-exports для обратной совместимости; все реальные импорты в новом коде должны быть `from app.utils.<module> import <symbol>`.
- **Почему:** R-77. Ускоряет collect-time тестов, упрощает refactoring.
- **Как:** В `app/utils/__init__.py` оставить:
  ```python
  # Deprecated: use specific imports.
  # Этот файл сохранён только для обратной совместимости.
  import warnings
  warnings.warn(
      "Importing from 'app.utils' is deprecated; "
      "use 'from app.utils.<module> import <symbol>' instead.",
      DeprecationWarning,
      stacklevel=2,
  )
  from app.utils.security import *  # noqa
  from app.utils.auth import *  # noqa
  # ... etc
  ```
- **Что проверять:**
  - Все существующие тесты проходят.
  - `pytest --collect-only` показывает < 1 с.

---

### Фаза 1 — Критичные исправления безопасности (hot-fixes)

#### Task 1.1 — Убрать логирование префикса JWT-секрета
- **Task ID:** `1.1`
- **Что меняется:**
  - `app/config.py:36-37` — заменить на `logger.debug('PGRST_JWT_SECRET loaded: length=%d', len(PGRST_JWT_SECRET))`.
  - `app/utils/auth.py:96-99` — удалить строку `current_app.logger.info('JWT: signing with secret prefix=%s...', secret[:8], ...)` целиком.
- **Почему:** SEC-1, SEC-2, R-2. Префикс секрета утекает в логи на каждом JWT-запросе.
- **Как:** Прямая правка двух строк.
- **Что проверять:**
  - `grep -r "secret\[:8\]\|secret\[:16\]" app/` возвращает 0 строк.
  - `grep -r "PGRST_JWT_SECRET\[:.*\]" app/` возвращает 0 строк.
  - Запуск приложения в DEBUG не выводит секрет в лог.

#### Task 1.2 — Убрать хардкод-фолбэки для `SECRET_KEY`
- **Task ID:** `1.2`
- **Что меняется:**
  - `websocket_server/auth.py:17` — `SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")` → `SECRET_KEY = os.environ["SECRET_KEY"]` (KeyError, если не задан).
  - `app/services/email_service.py:442` — `secret = os.environ.get("SECRET_KEY", "fallback-secret-key")` → `secret = current_app.config["SECRET_KEY"]` (через Flask context) или `secret = os.environ["SECRET_KEY"]`.
- **Почему:** SEC-4, SEC-5. Если env забыт в проде, приложение молча подписывает токены предсказуемым ключом.
- **Как:** Прямая замена; в `Dockerfile`/`docker-compose.yml`/`amvera.yaml` убедиться, что `SECRET_KEY` есть в env (если его нет — fail-fast на старте).
- **Что проверять:**
  - Без `SECRET_KEY` в env приложение падает при запуске с понятной ошибкой.
  - С `SECRET_KEY` в env — запускается как прежде.

#### Task 1.3 — Отделить `ADMIN_API_TOKEN` от `SECRET_KEY`, запретить empty-token CSRF bypass
- **Task ID:** `1.3`
- **Что меняется:** `app/__init__.py:199-237` (CSRF-exemption для admin-API).
- **Почему:** SEC-11, R-3. `hmac.compare_digest('', '') == True` — если оба токена пустые, проверка проходит.
- **Как:**
  ```python
  # app/__init__.py:199-237 — патч:
  ADMIN_API_TOKEN = app.config.get('ADMIN_API_TOKEN')
  if not ADMIN_API_TOKEN:
      app.logger.warning("ADMIN_API_TOKEN not set; admin-API endpoints disabled")

  @app.before_request
  def csrf_check():
      if request.method in ('GET', 'HEAD', 'OPTIONS'):
          return None
      if request.path in ('/api/reset-users', '/api/fix-permissions', '/api/reset-circuit-breaker'):
          # Admin-API: require X-Admin-Token, NOT SECRET_KEY fallback
          if not ADMIN_API_TOKEN:
              app.logger.error("Admin-API endpoint called without ADMIN_API_TOKEN configured")
              abort(403)
          token = request.headers.get('X-Admin-Token', '')
          if not token:
              abort(403)
          if not hmac.compare_digest(token, ADMIN_API_TOKEN):
              abort(403)
          return None
      # ... остальная CSRF-логика без изменений
  ```
- **Что проверять:**
  - Без `ADMIN_API_TOKEN` в env — `/api/reset-users` возвращает 403.
  - С корректным `X-Admin-Token` — 200.
  - С пустым `X-Admin-Token` и пустым `ADMIN_API_TOKEN` — 403 (раньше было 200).

#### Task 1.4 — Переставить порядок декораторов
- **Task ID:** `1.4`
- **Что меняется:** Во всех blueprint'ах поменять порядок на `@rate_limit` (внешний) → `@login_required` → `@role_required`. Конкретно:
  - `app/blueprints/jobs.py:432-565` (`job_new`)
  - `app/blueprints/jobs.py:877-1019` (`edit_job`)
  - `app/blueprints/applications.py:18` (`apply_job`)
  - `app/blueprints/profile.py:81` (`update_profile`), `:200` (`change_password`)
  - `app/blueprints/auth.py:187` (`login`), `:280` (`register`)
  - `app/blueprints/chat.py:95` (`send_message`)
- **Почему:** SEC-30, R-40. Python применяет декораторы снизу вверх: `@role_required` срабатывает раньше `@rate_limit` → PostgREST-запрос на role = бесплатный DoS-вектор.
- **Как:** Поменять местами декораторы. Пример:
  ```python
  # Было:
  @bp.route('/job/new', methods=['GET', 'POST'])
  @login_required
  @role_required('employer')
  @rate_limit(limit=10, window=60)
  def job_new():
      ...

  # Стало:
  @bp.route('/job/new', methods=['GET', 'POST'])
  @rate_limit(limit=10, window=60)        # внешний: first guard
  @login_required                          # средний: session check
  @role_required('employer')              # внутренний: DB check last
  def job_new():
      ...
  ```
- **Что проверять:**
  - `pytest tests/test_rate_limit.py` проходит.
  - При 11-м запросе на `/job/new` за 60 с — 429 (раньше делался PostgREST-запрос).

#### Task 1.5 — Запретить GET на мутирующих роутах
- **Task ID:** `1.5`
- **Что меняется:**
  - `app/blueprints/applications.py:18` — `methods=['GET', 'POST']` → `methods=['POST']`.
  - `app/blueprints/jobs.py:672` (`/cancel-job`) — `methods=['GET', 'POST']` → `methods=['POST']`.
  - `app/blueprints/jobs.py:726` (`/restore-job`) — то же.
  - `app/blueprints/jobs.py:824` (`/delete-job`) — то же.
- **Почему:** SEC-18, R-36. GET на мутирующих действиях = CSRF через `<img src=...>` и случайные клики краулеров.
- **Как:** Прямая правка `methods=[...]`. В шаблонах убедиться, что эти действия вызываются через `<form method="POST">` с CSRF-токеном (проверить `templates/my_jobs.html`, `templates/job_detail.html`).
- **Что проверять:**
  - `curl http://localhost:5000/apply/<uuid>` возвращает 405.
  - `curl -X POST http://localhost:5000/apply/<uuid>` работает как прежде.

#### Task 1.6 — Добавить `@role_required('worker')` на `apply_job`
- **Task ID:** `1.6`
- **Что меняется:** `app/blueprints/applications.py:18-83` — добавить `@role_required('worker')` поверх `@login_required`.
- **Почему:** SEC-30, R-9. Сейчас работодатель может откликнуться на вакансию другого работодателя.
- **Как:** Добавить декоратор. Убедиться, что `app/decorators.py:role_required` корректно работает для роли `worker`.
- **Что проверять:**
  - Работодатель, пытающийся откликнуться на вакансию — 403.
  - Worker может откликнуться как прежде.

#### Task 1.7 — WebSocket: убрать wildcard CORS, передать JWT не в URL, унифицировать secret + claim
- **Task ID:** `1.7`
- **Что меняется:**
  - `websocket_server/main.py:41-42, 200-206` — `allow_credentials=True` только если origin-list не `*`; дефолт — `["https://trudnik-hyperstls.amvera.io"]` (или из env `WEBSOCKET_CORS_ORIGINS`).
  - `websocket_server/main.py:54, 213-239` — убрать чтение `?token=` из URL; принимать JWT первым WebSocket-сообщением после handshake.
  - `websocket_server/auth.py:17, 33, 35` — использовать `PGRST_JWT_SECRET` (не `SECRET_KEY`); проверять claim `sub` (не `user_id`).
  - `app/context_processors.py:121-147` — генерировать WS-JWT с тем же секретом `PGRST_JWT_SECRET`, claim `sub`, TTL 15 минут (не 7 дней).
  - `app/context_processors.py:134-142` — НЕ инжектить WS-JWT в `window.TRUDNIK_CONFIG` напрямую. Вместо этого — endpoint `/api/ws-token` (с `@login_required`), который возвращает краткоживущий токен; фронтенд запрашивает его перед открытием WS.
  - `templates/base.html:555-560` — обновить JS-логику: при коннекте к WS сначала `fetch('/api/ws-token')`, потом отправить токен первым сообщением.
  - `websocket_server/main.py:213-239` — заменить `active_connections: dict[str, WebSocket]` на `dict[str, list[WebSocket]]` для multi-tab.
- **Почему:** SEC-13, SEC-14, SEC-15, SEC-16. WS-аутентификация сейчас полностью сломана; любой XSS утаскивает 7-дневный токен.
- **Как:** Большой рефакторинг; делать отдельным PR. Сохранять обратную совместимость: если `PGRST_JWT_SECRET` не задан — fail-fast.
- **Что проверять:**
  - `pytest tests/test_websocket_auth.py` проходит.
  - В логах nginx нет `?token=...` в URL WS-хендшейка.
  - Два устройства могут держать WS-коннект одновременно (multi-tab).
  - Через 16 минут после логина WS-коннект закрывается (токен истёк).

#### Task 1.8 — Logout: блэклист `jti` + чистить Service Worker кэш
- **Task ID:** `1.8`
- **Что меняется:**
  - `app/blueprints/auth.py:442-455` — после `session.clear()` добавить `add_to_jti_blacklist(session.get('jti'), ttl=<remaining lifetime>)`.
  - `app/utils/auth.py:114-154` — в `refresh_access_token` блэклистить старый `jti` перед выдачей нового.
  - `static/sw.js:58-67` — добавить `self.skipWaiting()` в `activate` handler; в `templates/base.html` слушать `controllerchange` и форсировать `window.location.reload()` один раз после logout.
- **Почему:** SEC-1, R-10, R-11. Logout не отзывает JWT; SW продолжает отдавать кэшированный HTML.
- **Как:** Прямые правки.
- **Что проверять:**
  - После logout старый JWT возвращает 401 на PostgREST-запросах (RLS-через PostgREST).
  - После logout страница перезагружается с пустым кэшем SW.

#### Task 1.9 — Санитизация email перед PostgREST URL
- **Task ID:** `1.9`
- **Что меняется:**
  - `app/blueprints/auth.py:536` — обернуть `email` в `sanitize_postgrest(email)` перед вставкой в URL.
  - Грепом найти все `f'...?email=eq.{...}'` в `app/` и применить `sanitize_postgrest`.
- **Почему:** SEC-19, R-23. PostgREST special chars (`,`, `&`, `:`) в email могут инжектить query-логику.
- **Как:** Использовать существующий `app/utils/security.py:sanitize_postgrest`. Дополнительно — расширить whitelist до `[^a-zA-Z0-9@._+-]`.
- **Что проверять:**
  - `pytest tests/test_sanitize.py` расширен тестами `email` с `,&:` — все должны давать пустой результат или sanitised.

#### Task 1.10 — Ограничить charset админ-поиска
- **Task ID:** `1.10`
- **Что меняется:** `app/blueprints/admin.py:106-116`.
- **Почему:** SEC-20, R-25. `ilike.*...*` принимает `|`, `(`, `)` → OR-conditions.
- **Как:**
  ```python
  import re
  search = request.args.get('search', '').strip()
  # Оставить только безопасные символы: буквы (вкл. кириллицу), цифры, пробел, дефис
  search = re.sub(r'[^а-яёА-ЯЁa-zA-Z0-9 \-]', '', search)[:100]
  if not search:
      users = []
  else:
      sanitized = sanitize_postgrest(search)
      # ... существующий запрос
  ```
- **Что проверять:**
  - `pytest tests/test_admin_browser.py` расширен тестом с `search='(|admin)'` — возвращает 0 результатов, не падает.

#### Task 1.11 — XSS-исправления в шаблонах
- **Task ID:** `1.11`
- **Что меняется:**
  - `templates/job_detail.html:522` — `{{ raterName }}` → `{{ raterName|e }}`.
  - `templates/base.html:738, 964-966` — flash-сообщения: `{{ msg }}` → `{{ msg|e }}`; для `data-flash` атрибутов — `|tojson|e`.
  - `templates/admin.html:510-513` — `value="${s.name}"` → `value="{{ s.name|e }}"`.
  - `templates/_filter_skills.html:143-145` — применить `|e` к интерполяциям.
  - Убедиться, что Jinja2 autoescape включён глобально (Flask включает по умолчанию; проверить отсутствие `{% autoescape false %}` блоков).
- **Почему:** SEC-17, R-27.
- **Как:** Прямые правки шаблонов. UI не меняется.
- **Что проверять:**
  - Ввести в `full_name` пользователя `<script>alert(1)</script>` → на admin-странице отображается как текст, не выполняется.
  - `pytest tests_e2e/test_admin_pages.py` проходит.

#### Task 1.12 — `/uploads/` path traversal + auth
- **Task ID:** `1.12`
- **Что меняется:**
  - `app/__init__.py:368-372` — использовать **абсолютный** путь: `upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])`.
  - Whitelist расширений: разрешить только `pdf, jpg, jpeg, png, webp` (для verification documents) и `jpg, png, webp` (для аватаров).
  - Для verification documents — добавить `@login_required` + ownership-check (пользователь может смотреть только свои документы; админ — все).
  - Для аватаров — оставить публичными (они отображаются в публичных профилях).
  - `app/services/storage_service.py:36-121` — усилить MIME-сниффинг: проверить первые 16 байт файла против известных сигнатур (JPEG `FFD8FF`, PNG `89504E47`, PDF `25504446`, WebP `52494646...57454250`); не доверять расширению.
  - Максимальный размер: `MAX_UPLOAD_SIZE = 5 * 1024 * 1024` (уже есть; проверить, что применяется до записи на диск).
- **Почему:** SEC-9, R-30.
- **Как:** Разделить `/uploads/avatars/` (публичные) и `/uploads/verification/` (auth required + ownership). Добавить blueprint-роут `@bp.route('/uploads/verification/<path:filename>')` с `@login_required` + ownership-check.
- **Что проверять:**
  - `curl http://localhost:5000/uploads/verification/<uuid>.pdf` без cookie → 401.
  - `curl .../uploads/avatars/<uuid>.jpg` без cookie → 200 (публичные).
  - `curl '.../uploads/../../../etc/passwd'` → 404.

#### Task 1.13 — Валидация длины полей профиля + UUID + content length в chat
- **Task ID:** `1.13`
- **Что меняется:**
  - `app/blueprints/profile.py:70-138` — добавить `MAX_LENGTHS = {'full_name': 150, 'phone': 20, 'city': 100, 'portfolio_link': 500, 'bio': 2000}`; валидировать перед INSERT.
  - `app/blueprints/chat.py:92-167` — `data = request.get_json(silent=True) or {}`; `application_id = data.get('application_id')`; `try: uuid.UUID(application_id) except ValueError: abort(400)`; `content = data.get('content', '').strip()[:5000]` (max 5000 символов).
- **Почему:** SEC-31, SEC-32, R-31, R-32.
- **Как:** Прямые правки.
- **Что проверять:**
  - `pytest tests/test_chat.py` расширен тестом с `application_id='not-a-uuid'` → 400.
  - Отправка 10 КБ сообщения → обрезается до 5000 символов.

#### Task 1.14 — `@validate_uuid` на десятках роутов
- **Task ID:** `1.14`
- **Что меняется:** Применить существующий декоратор `@validate_uuid('<param_name>')` из `app/utils/security.py` к:
  - `app/blueprints/jobs_api.py:106, 164` (`invite_worker`, `respond_invitation`)
  - `app/blueprints/applications.py:526-585` (`api_batch_applications` — для каждого `job_id`)
  - `app/blueprints/admin.py:272-308, 311-342, 445-497, 616-662` (bulk-delete — для каждого ID)
  - `app/blueprints/jobs.py:999-1016` (`add_favorite_job`, `remove_favorite_job`)
  - `app/blueprints/favorites.py:47-60` (`add_favorite`, `remove_favorite`)
  - `app/blueprints/blacklist.py:43, 60` (`block_user`, `unblock_user`)
  - `app/blueprints/employers.py:94, 150` (`employer_detail`, `toggle_favorite`)
  - `app/blueprints/notifications.py:58, 81` (`api_delete_notification`, `mark_read_route`)
  - `app/blueprints/admin.py:409-430, 578-614` (`update_skill`, `update_religion`, `delete_religion`)
- **Почему:** SEC-31, R-33.
- **Как:** Поочерёдно добавить декоратор. Для batch-эндпоинтов — валидировать каждый элемент списка в теле функции.
- **Что проверять:**
  - `pytest tests/test_api.py` расширен тестами с невалидными UUID → 400 на каждом роуте.

#### Task 1.15 — Закрыть anonymous-доступ к sensitive endpoints
- **Task ID:** `1.15`
- **Что меняется:**
  - `app/__init__.py:432-466` — `/health/postgrest` и `/health/circuit-breaker` требуют `X-Admin-Token` (constant-time compare). Оставить публичным только `/health` (boolean).
  - `app/blueprints/notifications.py:160-165` — `/push/vapid-public-key` требует `@login_required`.
  - `app/blueprints/jobs_api.py:33-99, 164-240` — `/api/skills`, `/api/religions`, `/api/search_jobs`, `/api/search_workers` требуют `@login_required`.
  - `app/blueprints/ratings.py:10-35, 38-55, 205-293` — ratings endpoints требуют `@login_required`.
  - `app/blueprints/profile.py:292` — `public_profile` требует `@login_required` (или сделать explicitly public с пометкой).
- **Почему:** SEC-26, R-37, R-38. Anonymous-scraping векторы.
- **Как:** Прямые правки декораторов.
- **Что проверять:**
  - `curl http://localhost:5000/health/postgrest` без `X-Admin-Token` → 403.
  - `curl http://localhost:5000/health` → 200 (публичный, только boolean).

#### Task 1.16 — Удалить хардкод admin email и test password `changeme123`
- **Task ID:** `1.16`
- **Что меняется:**
  - `app/blueprints/admin.py:862-998` — `/api/reset-users` обернуть в `if app.config.get('TEST_USER_PASSWORD') and current_app.config.get('DEPLOYMENT_ENV') != 'production':`.
  - `migrations/067_bootstrap_amvera.sql:2314-2323` — оставить как есть (миграция уже применена;改动 через новую миграцию 076, которая только обновляет email из env-переменной при запуске).
- **Почему:** SEC-23, SEC-24, R-4.
- **Как:** В `admin.py` добавить env-gate. В новой аддитивной миграции `076_seed_admin_from_env.sql` — `UPDATE profiles SET email = current_setting('app.admin_email', true) WHERE role = 'admin';` (вызывается вручную, не автоматически).
- **Что проверять:**
  - В проде `/api/reset-users` возвращает 403.
  - В dev (с `TEST_USER_PASSWORD` в env) — работает.

#### Task 1.17 — Аудит-лог: писать `user_id` администратора + покрывать bulk-actions
- **Task ID:** `1.17`
- **Что меняется:**
  - `app/blueprints/admin.py:19` — `log_admin_action` использовать `session.get('user_id') or current_app.config.get('SYSTEM_USER_ID')` (никогда не `None`).
  - Добавить `log_admin_action(...)` в `bulk_delete_users` (`admin.py:272-308`), `bulk_delete_jobs` (`:311-342`), `fix_permissions` (`:745-824`), `reset_users` (`:862-998`), `delete_job_admin` (`:211-232`), `delete_user` (`:260-267`).
- **Почему:** SEC-12, R-26, R-41. Bulk-actions сейчас вообще не логируются.
- **Как:** Прямые вставки `log_admin_action(action='bulk_delete_users', entity_type='profiles', entity_ids=ids, ...)`.
- **Что проверять:**
  - После bulk-delete в `audit_log` появляется запись с `user_id` админа и списком удалённых ID.

#### Task 1.18 — `/api/fix-permissions`: ограничить, rate-limit, audit-log
- **Task ID:** `1.18`
- **Что меняется:** `app/blueprints/admin.py:745-824`.
- **Почему:** SEC-12, R-26. Прямые `GRANT` SQL, защищённые только `X-Admin-Token`, без rate-limit и audit-log.
- **Как:**
  - Добавить `@rate_limit(limit=2, window=3600)` (2 раза в час — emergency-only).
  - Явно вызвать `log_admin_action(action='fix_permissions', ...)`.
  - В response возвращать список выполненных GRANT.
  - Опционально: выключить endpoint в проде через `if current_app.config.get('DEPLOYMENT_ENV') == 'production': abort(403)`.
- **Что проверять:**
  - `pytest tests/test_admin_browser.py` расширен тестом: 3-й вызов за час → 429.

#### Task 1.19 — Open redirect через `request.referrer`
- **Task ID:** `1.19`
- **Что меняется:**
  - Создать хелпер `app/utils/helpers.py:safe_redirect(target, fallback_endpoint)`, который проверяет, что `target` начинается с `/` и не с `//`.
  - Заменить `redirect(request.referrer or url_for(...))` на `safe_redirect(request.referrer, 'jobs.index')` в `favorites.py:53`, `blacklist.py:53,57`, `employers.py:175,177`, `jobs.py:1006,1016`.
- **Почему:** SEC-22, R-14.
- **Как:**
  ```python
  def safe_redirect(target: str | None, fallback_endpoint: str) -> Response:
      if target and target.startswith('/') and not target.startswith('//'):
          return redirect(target)
      return redirect(url_for(fallback_endpoint))
  ```
- **Что проверять:**
  - `pytest tests/test_security.py` расширен тестом: `Referer: https://evil.com/` → редирект на fallback.

#### Task 1.20 — Bugfix: `email_service._time_module.timedelta` + `auth.py:send_email` import
- **Task ID:** `1.20`
- **Что меняется:**
  - `app/services/email_service.py:114` — `_time_module.timedelta(days=1)` → `datetime.timedelta(days=1)` (использовать `datetime`, не `time`).
  - `app/blueprints/auth.py:551-562` — `from app.services.email_service import send_email` не работает. Заменить на:
    ```python
    from app.services.email_service import EmailService
    # ... внутри функции:
    email_service = EmailService()
    email_service.send_email(
        to_email=user_email,
        subject='Восстановление пароля',
        text_body=render_template('email/password_reset.txt', reset_link=reset_link, user_name=user_name),
        html_body=render_template('email/password_reset.html', reset_link=reset_link, user_name=user_name),
    )
    ```
    (Уточнить сигнатуру `EmailService.send_email` в `app/services/email_service.py`.)
- **Почему:** SEC-6, SEC-7. Password-reset flow полностью сломан.
- **Как:** Прямая правка + unit-тест.
- **Что проверять:**
  - `pytest tests/test_email_service.py` проходит с test SMTP-сервером.
  - `pytest tests/test_auth.py` — password-reset flow отправляет email.

#### Task 1.21 — Ownership-чеки для `delete_photo`, password confirmation для `delete_account`, role-check для `verify_employer`
- **Task ID:** `1.21`
- **Что меняется:**
  - `app/blueprints/profile.py:141-169` (`delete_photo`) — добавить ownership-check: `if photo.user_id != session['user_id']: abort(403)` (или через PostgREST-запрос `?id=eq.{photo_id}&user_id=eq.{session['user_id']}`).
  - `app/blueprints/profile.py:172-197` (`delete_account`) — требовать поле `password` в форме; проверить через `check_password(session['password_hash'], request.form['password'])`.
  - `app/blueprints/profile.py:253-289` (`verify_employer`) — добавить `@role_required('employer')` + проверку `verification_status in ('none', 'rejected')`.
- **Почему:** SEC-27, SEC-28, SEC-29, R-69.
- **Как:** Прямые правки.
- **Что проверять:**
  - `pytest tests/test_avatar_upload.py` расширен: user A не может удалить фото user B.
  - `pytest tests/test_auth.py` расширен: `delete_account` без пароля → 400.

#### Task 1.22 — Заменить DELETE notifications по `ilike` на relational columns
- **Task ID:** `1.22`
- **Что меняется:**
  - Новая аддитивная миграция `077_notifications_entity_columns.sql`:
    ```sql
    ALTER TABLE notifications
        ADD COLUMN IF NOT EXISTS entity_type text,
        ADD COLUMN IF NOT EXISTS entity_id uuid;
    CREATE INDEX IF NOT EXISTS idx_notifications_entity
        ON notifications(entity_type, entity_id);
    ```
  - `app/services/notification_service.py` — при `create()` заполнять `entity_type` ('job', 'application', 'invitation') и `entity_id`.
  - `app/blueprints/jobs.py:854-858` — заменить `message=ilike.*{job_id}*` на `entity_type=eq.job&entity_id=eq.{job_id}`.
  - `app/blueprints/notifications.py:70-78` — заменить `not.ilike.*вас пригласили*` на `entity_type=neq.invitation`.
- **Почему:** SEC-32, R-34. Паттерн-ориентированное удаление хрупко и race-prone.
- **Как:** Миграция аддитивная (старые записи получат NULL в `entity_type` — это нормально; новые — заполненные). Код gracefully обрабатывает оба случая.
- **Что проверять:**
  - Старые уведомления (с NULL entity) остаются в БД.
  - Новые уведомления корректно удаляются при delete-job.

---

### Фаза 2 — Ядро бизнес-логики (services + repositories + use cases)

#### Task 2.1 — Иерархия исключений `app/errors.py`
- **Task ID:** `2.1`
- **Что меняется:** Новый файл `app/errors.py`.
- **Почему:** R-63, R-72. 50+ bare `except Exception` swallow real errors; нет единого контракта ошибок.
- **Как:**
  ```python
  # app/errors.py
  class AppError(Exception):
      """Base class for all application errors."""
      status_code = 500
      code = 'internal_error'

      def __init__(self, message: str = '', *, payload: dict | None = None):
          super().__init__(message)
          self.message = message
          self.payload = payload or {}

  class DomainError(AppError):
      """4xx errors: business rule violations."""
      status_code = 400

  class NotFoundError(DomainError):
      status_code = 404
      code = 'not_found'

  class PermissionDeniedError(DomainError):
      status_code = 403
      code = 'permission_denied'

  class ValidationFailedError(DomainError):
      status_code = 422
      code = 'validation_failed'

  class ConflictError(DomainError):
      status_code = 409
      code = 'conflict'

  class ApplyJobError(DomainError):
      code = 'apply_job_failed'

  class DuplicateApplication(ConflictError):
      code = 'duplicate_application'

  class NoSlotsAvailable(ConflictError):
      code = 'no_slots_available'

  class BlacklistedByEmployer(PermissionDeniedError):
      code = 'blacklisted'

  class InfrastructureError(AppError):
      """5xx errors: infrastructure failures."""
      status_code = 502

  class PostgrestError(InfrastructureError):
      code = 'postgrest_error'

  class CircuitBreakerOpenError(InfrastructureError):
      status_code = 503
      code = 'circuit_breaker_open'

  class RedisUnavailableError(InfrastructureError):
      status_code = 503
      code = 'redis_unavailable'
  ```

#### Task 2.2 — Централизованный `app/error_handlers.py`
- **Task ID:** `2.2`
- **Что меняется:** Новый файл `app/error_handlers.py`. Регистрация в `create_app()`.
- **Почему:** R-63, R-72. Единый контракт ошибок: JSON для `/api/*`, flash+redirect для HTML.
- **Как:**
  ```python
  # app/error_handlers.py
  from flask import jsonify, request, flash, redirect, url_for, render_template
  from app.errors import AppError, DomainError, InfrastructureError
  import uuid, logging

  _logger = logging.getLogger(__name__)

  def register_error_handlers(app):
      @app.errorhandler(DomainError)
      def _handle_domain(e: DomainError):
          if request.path.startswith('/api/'):
              return jsonify({'error': {'code': e.code, 'message': e.message, 'payload': e.payload}}), e.status_code
          flash(e.message or 'Ошибка', 'error')
          return redirect(request.referrer or url_for('jobs.index'))

      @app.errorhandler(InfrastructureError)
      def _handle_infra(e: InfrastructureError):
          support_id = str(uuid.uuid4())
          _logger.exception('InfrastructureError support_id=%s: %s', support_id, e)
          if request.path.startswith('/api/'):
              return jsonify({'error': {'code': e.code, 'support_id': support_id}}), e.status_code
          return render_template('error.html', code=e.status_code, support_id=support_id), e.status_code

      @app.errorhandler(Exception)
      def _handle_unknown(e):
          support_id = str(uuid.uuid4())
          _logger.exception('Unhandled exception support_id=%s: %s', support_id, e)
          if request.path.startswith('/api/'):
              return jsonify({'error': {'code': 'internal_error', 'support_id': support_id}}), 500
          return render_template('error.html', code=500, support_id=support_id), 500
  ```
  В `create_app()` добавить `register_error_handlers(app)`.
- **Что проверять:**
  - `pytest tests/test_architecture.py` расширен: бросок `DomainError` в `/api/*` возвращает JSON с правильным `code`.
  - Бросок `Exception` в HTML-роутах рендерит `error.html` с `support_id`.

#### Task 2.3 — Repository pattern: `app/repositories/`
- **Task ID:** `2.3`
- **Что меняется:** Новые файлы: `app/repositories/__init__.py`, `app/repositories/base.py`, `app/repositories/job_repository.py`, `app/repositories/application_repository.py`, `app/repositories/admin_repository.py`, `app/repositories/notification_repository.py`.
- **Почему:** R-73. Сейчас ~80 call sites `postgrest_request`/`postgrest_admin_request` разбросаны по blueprint'ам и services; нет единой точки для кэширования, аудита, логирования.
- **Как:**
  ```python
  # app/repositories/base.py
  from app.utils.postgrest_client import postgrest_request, postgrest_admin_request
  from app.cache import redis_cache_get, redis_cache_set, redis_cache_delete

  class BaseRepository:
      table: str = ''
      use_admin: bool = False  # если True — использовать service-role (RLS bypass)

      def _request(self, method, path, **kwargs):
          fn = postgrest_admin_request if self.use_admin else postgrest_request
          return fn(method, path, **kwargs)

      def get_by_id(self, id_: str, select: str = '*'):
          resp = self._request('GET', f'{self.table}?id=eq.{id_}&select={select}')
          data = resp.json() if resp.ok else []
          return data[0] if data else None

      def list(self, filters: str = '', select: str = '*', limit: int = 50, offset: int = 0, order: str = 'created_at.desc'):
          path = f'{self.table}?{filters}&select={select}&order={order}&limit={limit}&offset={offset}'
          resp = self._request('GET', path)
          return resp.json() if resp.ok else []

  # app/repositories/job_repository.py
  class JobRepository(BaseRepository):
      table = 'jobs'
      use_admin = False  # RLS-protected; user-token

      def get_with_references(self, job_id: str):
          """Single PostgREST call replacing 5 sequential queries in job_detail."""
          select = '*,photos:job_photos(*),employer:profiles!jobs_employer_id_fkey(*),applications:applications(count,worker_id)'
          path = f'jobs?id=eq.{job_id}&select={select}'
          resp = self._request('GET', path)
          data = resp.json() if resp.ok else []
          return data[0] if data else None

  # app/repositories/admin_repository.py
  class AdminRepository(BaseRepository):
      table = 'profiles'
      use_admin = True

      def get_stats(self):
          """Single RPC call replacing 8 count=exact queries."""
          cached = redis_cache_get('admin:stats')
          if cached:
              return cached
          resp = postgrest_admin_request('POST', '/rpc/get_admin_stats')
          stats = resp.json() if resp.ok else {}
          redis_cache_set('admin:stats', stats, ttl=60)
          return stats
  ```
  В `app/container.py` (см. Task 2.6) зарегистрировать `job_repo = JobRepository()` и т.д.
- **Что проверять:**
  - `pytest tests/test_architecture.py` — `JobRepository.get_with_references` делает 1 HTTP-запрос вместо 5.
  - `pytest tests/test_admin_browser.py` — dashboard грузится < 100 мс (раньше 500–800 мс).

#### Task 2.4 — Migration `076_get_admin_stats.sql`
- **Task ID:** `2.4`
- **Что меняется:** Новый файл `migrations/076_get_admin_stats.sql` (аддитивный, не деструктивный).
- **Почему:** BN-1, R-42, R-73. Заменяет 8 последовательных `count=exact` запросов одним RPC.
- **Как:**
  ```sql
  -- migrations/076_get_admin_stats.sql
  CREATE OR REPLACE FUNCTION public.get_admin_stats()
  RETURNS jsonb
  LANGUAGE sql
  SECURITY DEFINER
  SET search_path = public
  AS $$
    SELECT jsonb_build_object(
      'total_users', (SELECT count(*) FROM profiles),
      'workers', (SELECT count(*) FROM profiles WHERE role = 'worker'),
      'employers', (SELECT count(*) FROM profiles WHERE role = 'employer'),
      'admins', (SELECT count(*) FROM profiles WHERE role = 'admin'),
      'total_jobs', (SELECT count(*) FROM jobs),
      'open_jobs', (SELECT count(*) FROM jobs WHERE status = 'open'),
      'closed_jobs', (SELECT count(*) FROM jobs WHERE status = 'closed'),
      'cancelled_jobs', (SELECT count(*) FROM jobs WHERE status = 'cancelled'),
      'pending_verifications', (SELECT count(*) FROM profiles WHERE role = 'employer' AND verification_status = 'pending'),
      'total_applications', (SELECT count(*) FROM applications),
      'unread_notifications', (SELECT count(*) FROM notifications WHERE is_read = false)
    );
  $$;

  GRANT EXECUTE ON FUNCTION public.get_admin_stats() TO trudnikapp, anon, authenticated;
  ```
  Не деструктивно: `CREATE OR REPLACE` + `GRANT`. Не трогает существующие таблицы.
- **Что проверять:**
  - `psql -f migrations/076_get_admin_stats.sql` проходит без ошибок.
  - `curl -X POST http://localhost:5000/rpc/get_admin_stats` возвращает JSON с 12 ключами.
  - `app/blueprints/admin.py:47-103` — переписать на `AdminRepository().get_stats()`; dashboard грузится < 100 мс.

#### Task 2.5 — Use Cases: `app/use_cases/`
- **Task ID:** `2.5`
- **Что меняется:** Новые файлы: `app/use_cases/__init__.py`, `app/use_cases/apply_job.py`, `app/use_cases/withdraw_application.py`, `app/use_cases/accept_invitation.py`, `app/use_cases/create_job.py`, `app/use_cases/cancel_job.py`.
- **Почему:** R-74, R-58, R-59. Вынести бизнес-логику из blueprint'ов в тестируемые классы; убрать `threading.Thread`; удалить TOCTOU fallback paths.
- **Как:**
  ```python
  # app/use_cases/apply_job.py
  from dataclasses import dataclass
  from app.errors import ApplyJobError, DuplicateApplication, NoSlotsAvailable, BlacklistedByEmployer
  from app.utils.postgrest_client import postgrest_rpc
  from app.services.notification_service import enqueue_notification

  @dataclass
  class ApplyJobCommand:
      worker_id: str
      job_id: str
      cover_letter: str = ''

  @dataclass
  class ApplyJobResult:
      application_id: str
      status: str

  class ApplyJobUseCase:
      def __init__(self, notification_service=None):
          self._notification_service = notification_service

      def execute(self, cmd: ApplyJobCommand) -> ApplyJobResult:
          resp = postgrest_rpc('POST', '/rpc/apply_job_atomic', json={
              'p_worker_id': cmd.worker_id,
              'p_job_id': cmd.job_id,
              'p_cover_letter': cmd.cover_letter,
          })
          if not resp.ok:
              self._raise_from_postgrest(resp)
          data = resp.json()
          # Enqueue notifications via Celery (not threading.Thread)
          enqueue_notification(
              user_id=data['employer_id'],
              notification_type='application_received',
              title='Новый отклик',
              message='Получен новый отклик на вакансию',
              entity_type='job',
              entity_id=cmd.job_id,
          )
          return ApplyJobResult(application_id=data['application_id'], status=data['status'])

      def _raise_from_postgrest(self, resp):
          try:
              err = resp.json()
          except Exception:
              err = {}
          code = err.get('code', '')
          msg = err.get('message', '').lower()
          if 'duplicate' in msg:
              raise DuplicateApplication('Вы уже откликнулись на эту вакансию')
          if 'no slots' in msg or 'no_slots' in msg:
              raise NoSlotsAvailable('Нет свободных слотов')
          if 'blacklist' in msg:
              raise BlacklistedByEmployer('Работодатель добавил вас в чёрный список')
          raise ApplyJobError(f'Apply job failed: {err.get("message", resp.text)}')
  ```
  В `app/blueprints/applications.py:apply_job` заменить тело на:
  ```python
  @bp.route('/apply/<job_id>', methods=['POST'])
  @rate_limit(limit=10, window=60)
  @login_required
  @role_required('worker')
  def apply_job(job_id):
      cmd = ApplyJobCommand(
          worker_id=session['user_id'],
          job_id=job_id,
          cover_letter=request.form.get('cover_letter', ''),
      )
      result = current_app.container.apply_job_use_case().execute(cmd)
      flash('Отклик отправлен', 'success')
      return redirect(url_for('jobs.job_detail', job_id=job_id))
  ```
  **Удалить** `_apply_job_fallback` и `threading.Thread` calls.
- **Что проверять:**
  - `pytest tests/test_job_lifecycle.py` проходит.
  - `grep -r "threading.Thread" app/blueprints/` возвращает 0 строк.
  - `grep -r "_apply_job_fallback" app/` возвращает 0 строк.

#### Task 2.6 — DI-контейнер `app/container.py`
- **Task ID:** `2.6`
- **Что меняется:** Новый файл `app/container.py`. Регистрация в `create_app()`.
- **Почему:** R-76. Зависимости (repositories, services, use cases) сейчас создаются inline; трудно тестировать.
- **Как:**
  ```python
  # app/container.py
  from dataclasses import dataclass
  from app.repositories.job_repository import JobRepository
  from app.repositories.application_repository import ApplicationRepository
  from app.repositories.admin_repository import AdminRepository
  from app.repositories.notification_repository import NotificationRepository
  from app.services.notification_service import NotificationService
  from app.use_cases.apply_job import ApplyJobUseCase

  @dataclass
  class Container:
      job_repo: JobRepository
      application_repo: ApplicationRepository
      admin_repo: AdminRepository
      notification_repo: NotificationRepository
      notification_service: NotificationService

      @classmethod
      def from_config(cls, config):
          return cls(
              job_repo=JobRepository(),
              application_repo=ApplicationRepository(),
              admin_repo=AdminRepository(),
              notification_repo=NotificationRepository(),
              notification_service=NotificationService(),
          )

      def apply_job_use_case(self):
          return ApplyJobUseCase(notification_service=self.notification_service)

  # В create_app():
  from app.container import Container
  app.container = Container.from_config(app.config)
  ```
  В blueprint'ах: `current_app.container.apply_job_use_case().execute(cmd)`.
- **Что проверять:**
  - `pytest tests/test_apply_job_use_case.py` — Use Case тестируется без Flask-контекста (с fake repository).

#### Task 2.7 — Рефакторинг `notification_service.create` (151 строка → 5 функций)
- **Task ID:** `2.7`
- **Что меняется:** `app/services/notification_service.py:76-227` разбить на:
  - `_check_user_prefs(user_id, notification_type) -> bool`
  - `_insert_notification(user_id, type, title, message, entity_type, entity_id) -> dict`
  - `_publish_to_redis(user_id, payload) -> None`
  - `_dispatch_email(user_id, payload) -> None` (через Celery)
  - `_dispatch_push(user_id, payload) -> None` (через Celery)
  - `create(...)` — оркестратор из 5 строк.
- **Почему:** R-66. Mixed concerns в одной функции.
- **Как:** Поочерёдная экстракция; после каждой — `pytest tests/test_notification_service.py`.
- **Что проверять:**
  - Все 5 приватных функций покрыты unit-тестами.
  - Поведение `create()` не изменилось.

#### Task 2.8 — Bugfixes в notification_service (title column, UUID types, NOTIFICATION_TYPES)
- **Task ID:** `2.8`
- **Что меняется:**
  - `app/services/notification_service.py:99-105` — `base_payload` добавить `title` (NOT NULL column in DB).
  - `app/tasks/email_tasks.py:24, 89` — `notification_id: int` → `notification_id: str` (UUID).
  - `app/services/notification_service.py:30-45` — добавить в `NOTIFICATION_TYPES`: `force_complete`, `invitation_accepted`, `application_cancelled`.
  - `app/services/notification_service.py:161-172` — убрать запрос к несуществующей колонке `username`; использовать `full_name`.
  - `app/tasks/celery_app.py:81-103` — добавить beat-задачу `cleanup-old-notifications` (вызывает `maintenance_tasks.cleanup_orphaned_notifications` раз в сутки).
- **Почему:** R-66. Notification flow частично сломан (отсутствие `title` → INSERT fails).
- **Как:** Прямые правки.
- **Что проверять:**
  - `pytest tests/test_notification_service.py` — INSERT с `title` проходит.
  - В `audit_log` Celery beat появляется `cleanup-old-notifications`.

#### Task 2.9 — Заменить `threading.Thread` на Celery в `apply_job`, `apply_selected`, `withdraw_application`, `accept_invitation`
- **Task ID:** `2.9`
- **Что меняется:**
  - `app/blueprints/applications.py:73-80, 172-179, 240-251` — убрать `threading.Thread(target=_notify_employer, daemon=True).start()`.
  - Использовать существующий `enqueue_notification()` (пишет в `notification_outbox`, обрабатывается Celery).
- **Почему:** SEC-10, R-58. Daemon-threads теряются при shutdown воркера.
- **Как:** Прямая замена. Логика уведомлений переезжает в Use Cases (Task 2.5).
- **Что проверять:**
  - `grep -r "threading.Thread" app/blueprints/` возвращает 0 строк.

#### Task 2.10 — `cache_for` на Redis
- **Task ID:** `2.10`
- **Что меняется:** `app/utils/postgrest_client.py:249-275`. Переписать `cache_for(seconds)` на Redis-бэкенд.
- **Почему:** BN-8, R-49, R-75. In-memory cache бесполезен под gunicorn; без eviction — утечка памяти.
- **Как:**
  ```python
  import pickle, hashlib, functools
  from app.cache import redis_cache_get, redis_cache_set

  def cache_for(seconds: int = 300):
      def decorator(func):
          @functools.wraps(func)
          def wrapper(*args, **kwargs):
              key_parts = [func.__module__, func.__name__]
              key_parts.extend(str(a) for a in args)
              key_parts.extend(f"{k}={v}" for k,v in sorted(kwargs.items()))
              key_str = '|'.join(key_parts)
              key = 'pf:' + hashlib.sha256(key_str.encode()).hexdigest()[:32]
              cached = redis_cache_get(key)
              if cached is not None:
                  return cached
              result = func(*args, **kwargs)
              redis_cache_set(key, result, ttl=seconds)
              return result
          return wrapper
      return decorator
  ```
- **Что проверять:**
  - `pytest tests/test_utils_unit.py` — `cache_for` работает.
  - При 4 gunicorn-воркерах кэш шарится между ними.

#### Task 2.11 — Thread-safe `requests.Session` + per-process SMTP
- **Task ID:** `2.11`
- **Что меняется:**
  - `app/utils/postgrest_client.py:232-242` — `_session` сделать через `requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)` с `threading.local()` для connector'а.
  - `app/services/email_service.py:75-165` — `self._smtp` создавать per-process (в Celery-task context, не в `__init__`); добавить `timeout=30` в `starttls()` и `login()`.
- **Почему:** BN-9, BN-10, R-50.
- **Как:** Прямая правка.
- **Что проверять:**
  - `pytest tests/test_email_service.py` проходит.
  - Нагрузочный тест (locust) — 100 параллельных запросов не вызывают `ConnectionError`.

#### Task 2.12 — Кэшировать JWT в session
- **Task ID:** `2.12`
- **Что меняется:** `app/utils/postgrest_client.py:319-339` `get_user_headers()`.
- **Почему:** BN-11, R-51. На каждый PostgREST-запрос подписывается новый JWT.
- **Как:**
  ```python
  def get_user_headers():
      from flask import session
      import time
      cached = session.get('pgrst_token')
      cached_exp = session.get('pgrst_token_exp', 0)
      if cached and cached_exp > time.time() + 30:
          return {'Authorization': f'Bearer {cached}', ...}
      token = generate_jwt(...)
      session['pgrst_token'] = token
      session['pgrst_token_exp'] = time.time() + 240  # 4 min (token TTL = 5 min)
      return {'Authorization': f'Bearer {token}', ...}
  ```
- **Что проверять:**
  - Логи Redis: `SETEX` на `pgrst_jti:*` — 1 раз в 4 минуты на пользователя (раньше — на каждый запрос).

#### Task 2.13 — Различать 5xx и 4xx в CircuitBreaker
- **Task ID:** `2.13`
- **Что меняется:** `app/utils/postgrest_client.py:102-127, 434-478`.
- **Почему:** R-52. CB открывается на любой 5xx, включая 4xx клиентских ошибок; `postgrest_request` ретраит 401 с 0.5s sleep.
- **Как:**
  ```python
  # Открывать CB только на 5xx
  if resp.status_code >= 500:
      breaker.record_failure()
  elif resp.status_code < 400:
      breaker.record_success()
  # 4xx — не влияет на CB

  # В postgrest_request: ретраить только 5xx (через tenacity), не 401
  # 401 — refresh token один раз, не ретраить
  ```
  Добавить `tenacity` в `requirements.txt`.
- **Что проверять:**
  - Имитация 422 от PostgREST — CB не открывается.
  - Имитация 503 — CB открывается после 10 ошибок.

#### Task 2.14 — Redis sliding-window rate-limit
- **Task ID:** `2.14`
- **Что меняется:** `app/decorators.py:rate_limit`. Реализовать sliding-window через Redis `ZSET`.
- **Почему:** BN-12, R-53.
- **Как:**
  ```python
  import time, functools
  from app.utils.redis_client import get_redis_client

  def rate_limit(limit: int = 60, window: int = 60, key_prefix: str = 'rl', fail_open: bool = True):
      def decorator(func):
          @functools.wraps(func)
          def wrapper(*args, **kwargs):
              from flask import request, session, abort
              user_id = session.get('user_id') or request.remote_addr
              key = f'{key_prefix}:{func.__module__}.{func.__name__}:{user_id}'
              now = time.time()
              client = get_redis_client()
              if not client:
                  if fail_open:
                      return func(*args, **kwargs)
                  abort(503, 'Rate limiter unavailable')
              pipe = client.pipeline()
              pipe.zremrangebyscore(key, 0, now - window)
              pipe.zadd(key, {f'{now}': now})
              pipe.zcard(key)
              pipe.expire(key, window)
              _, _, count, _ = pipe.execute()
              if count > limit:
                  abort(429, 'Rate limit exceeded')
              return func(*args, **kwargs)
          return wrapper
      return decorator
  ```
- **Что проверять:**
  - `pytest tests/test_rate_limit.py` — 11-й запрос за 60 с → 429.
  - Под 4 gunicorn-воркерами лимит общий.

---

### Фаза 3 — API и роуты (blueprints)

#### Task 3.1 — `admin_panel`: использовать `AdminRepository.get_stats()`
- **Task ID:** `3.1`
- **Что меняется:** `app/blueprints/admin.py:47-103` — заменить 8 последовательных `count=exact` запросов на `current_app.container.admin_repo.get_stats()`.
- **Почему:** BN-1, R-42.
- **Как:** Прямая замена; dashboard грузится из Redis-кэша (TTL 60s).
- **Что проверять:**
  - Dashboard грузится < 100 мс (раньше 500–800 мс).
  - После `redis_cache_delete('admin:stats')` — свежие данные.

#### Task 3.2 — `role_required`: кэшировать `session['role']`
- **Task ID:** `3.2`
- **Что меняется:** `app/decorators.py:67-88`.
- **Почему:** BN-2, R-43. На каждый защищённый запрос — PostgREST-запрос на role.
- **Как:**
  ```python
  def role_required(required_role):
      def decorator(func):
          @functools.wraps(func)
          def wrapper(*args, **kwargs):
              if 'role' not in session:
                  abort(403)
              cached_role = session.get('role')
              cached_at = session.get('role_checked_at', 0)
              import time
              if time.time() - cached_at > 300:  # revalidate every 5 min
                  resp = postgrest_request('GET', f'profiles?id=eq.{session["user_id"]}&select=role')
                  if not resp.ok or not resp.json():
                      abort(403)
                  cached_role = resp.json()[0]['role']
                  session['role'] = cached_role
                  session['role_checked_at'] = time.time()
              if cached_role != required_role and cached_role != 'admin':
                  abort(403)
              return func(*args, **kwargs)
          return wrapper
      return decorator
  ```
- **Что проверять:**
  - 100 последовательных запросов на `/my-jobs` — PostgREST делает 1 запрос на role (раньше — 100).

#### Task 3.3 — `job_detail`: один PostgREST-запрос с embedded resources
- **Task ID:** `3.3`
- **Что меняется:** `app/blueprints/jobs.py:353-415` — использовать `JobRepository.get_with_references(job_id)`.
- **Почему:** BN-4, R-46.
- **Как:** Прямая замена. Добавить обработку `None` (job not found → `NotFoundError`).
- **Что проверять:**
  - `job_detail` делает 1 HTTP-запрос (раньше — 5+).
  - `pytest tests/test_job_lifecycle.py` проходит.

#### Task 3.4 — `ratings.get_job_ratings`: одна агрегация
- **Task ID:** `3.4`
- **Что меняется:** `app/blueprints/ratings.py:19-35` — заменить 2 запроса на один с агрегацией.
- **Почему:** R-44.
- **Как:**
  ```python
  resp = postgrest_admin_request('GET',
      f'ratings?job_id=eq.{job_id}&select=*,rater:rater_id(full_name,photo_url),avg_rating:rating.avg()')
  ```
- **Что проверять:** 1 HTTP-запрос вместо 2.

#### Task 3.5 — `enrich_job_with_references`: убрать N+1
- **Task ID:** `3.5`
- **Что меняется:** `app/services/job_service.py:45-65` — для списков использовать embedded resources в исходном запросе; для одиночного job — оставить как есть.
- **Почему:** BN-3, R-45.
- **Как:** Перенести логику enrichment в `JobRepository.find_open()` через `select=*,work_type:skills(name),preferred_religion:religions(name)`.
- **Что проверять:**
  - `pytest tests/test_job_lifecycle.py` — список вакансий грузится без N+1.

#### Task 3.6 — `delete_job`: одна RPC вместо 7 DELETE
- **Task ID:** `3.6`
- **Что меняется:** `app/blueprints/jobs.py:824-864` — использовать существующую RPC `delete_job_cascade` (уже определена в `migrations/067_bootstrap_amvera.sql:1318`).
- **Почему:** BN-5, R-60.
- **Как:**
  ```python
  resp = postgrest_admin_request('POST', '/rpc/delete_job_cascade', json={'p_job_id': job_id})
  if not resp.ok:
      raise PostgrestError(f'delete_job_cascade failed: {resp.text}')
  ```
- **Что проверять:**
  - `pytest tests/test_job_lifecycle.py` — delete job делает 1 HTTP-запрос.
  - Все связанные записи (photos, ratings, notifications по entity) удалены.

#### Task 3.7 — Пагинация на `chat`, `my_applications`, `workers`
- **Task ID:** `3.7`
- **Что меняется:**
  - `app/blueprints/chat.py:58-66` — `limit=50&offset=<since_id>` (cursor-based).
  - `app/blueprints/applications.py:363-424` — `per_page=20`, cursor-based pagination.
  - `app/blueprints/jobs.py:272-350` (`workers`) — `per_page=20`.
- **Почему:** BN-6, R-47.
- **Как:** Cursor-based (использовать `id=gt.<last_id>&order=id.asc&limit=20`).
- **Что проверять:**
  - В UI появляется кнопка "Загрузить ещё" (минимальное UI-изменение, допустимо).
  - 1000 сообщений в чате — первая страница грузится < 200 мс.

#### Task 3.8 — `my_jobs`: убрать `detailed_description` из list-view
- **Task ID:** `3.8`
- **Что меняется:** `app/blueprints/jobs.py:580` — заменить `select=*` на явный список полей.
- **Почему:** R-55.
- **Как:** Прямая правка.
- **Что проверять:** Размер ответа `/my-jobs` уменьшился.

#### Task 3.9 — `admin_panel` users tab: убрать `password_hash` из select
- **Task ID:** `3.9`
- **Что меняется:** `app/blueprints/admin.py:119` — `select=id,email,full_name,role,verification_status,created_at,city,phone,photo_url,rating`.
- **Почему:** SEC-21, R-55.
- **Как:** Прямая правка.
- **Что проверять:** В response нет `password_hash`, `notification_prefs`, `bio`.

#### Task 3.10 — Кэшировать git-версию на старте
- **Task ID:** `3.10`
- **Что меняется:** `app/blueprints/admin.py:167-172`.
- **Почему:** BN-13, R-7.
- **Как:**
  ```python
  # В create_app():
  app.config['APP_VERSION'] = _read_git_version()

  def _read_git_version():
      try:
          import subprocess
          return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], timeout=2).decode().strip()
      except Exception:
          return os.environ.get('APP_VERSION', 'unknown')
  ```
- **Что проверять:**
  - 100 запросов на `/admin` — 0 вызовов `subprocess`.

#### Task 3.11 — Context processors: батчить в один Redis-cached счётчик
- **Task ID:** `3.11`
- **Что меняется:** `app/context_processors.py:150-266`.
- **Почему:** BN-14, R-48. На каждый рендер — 3+ PostgREST-запроса.
- **Как:**
  ```python
  @app.context_processor
  def inject_counters():
      user_id = session.get('user_id')
      if not user_id:
          return {}
      cached = redis_cache_get(f'user:counters:{user_id}')
      if cached is not None:
          return cached
      counters = _fetch_user_counters(user_id)
      redis_cache_set(f'user:counters:{user_id}', counters, ttl=30)
      return counters
  ```
  Инвалидация кэша — при мутации (новое уведомление → `redis_cache_delete(f'user:counters:{user_id}')`).
- **Что проверять:**
  - 100 запросов на `/` (залогиненный пользователь) — 1 PostgREST-запрос на counters (раньше — 300+).

#### Task 3.12 — `my_jobs_action` и `api_batch_applications`: вынести в Use Cases
- **Task ID:** `3.12`
- **Что меняется:**
  - `app/blueprints/jobs.py:600-641` — `BatchJobActionUseCase`.
  - `app/blueprints/applications.py:526-585` — `BatchApplicationActionUseCase`.
- **Почему:** R-67, R-68. Дублирование логики; рекурсия (`api_handle_application` для `reopen` вызывает `accept`).
- **Как:** Экстракция. Use Case принимает `BatchCommand` со списком ID и action; валидирует action против whitelist; валидирует UUIDs; rate-limit; проверяет `has_accepted` для delete.
- **Что проверять:**
  - `pytest tests/test_job_lifecycle.py` расширен batch-тестами.

#### Task 3.13 — `job_new`: field-specific error messages
- **Task ID:** `3.13`
- **Что меняется:** `app/blueprints/jobs.py:509-511, 561-562, 580-599`.
- **Почему:** R-64. `ValueError` от `float()/int()` глушится; `resp.text` показывается пользователю.
- **Как:** Каждый cast в `try/except (ValueError, TypeError)` с field-specific flash; `resp.text` только в `logger.warning`.
- **Что проверять:**
  - При вводе не-числа в `payment` — flash "Поле 'Оплата' должно быть числом".

#### Task 3.14 — Service Worker: не кэшировать HTML/API, починить `/offline?_sw_ping=`
- **Task ID:** `3.14`
- **Что меняется:** `static/sw.js:58-132`.
- **Почему:** SEC-15, R-57. SW кэширует HTML/API — утечка аутентифицированного контента; рекурсивный `/offline?_sw_ping=` fetch.
- **Как:**
  ```javascript
  // В fetch handler:
  if (request.mode === 'navigate' || request.url.includes('/api/')) {
      // network-first, без кэширования HTML/API
      return fetch(request).catch(() => caches.match('/offline'));
  }
  // Только статика — cache-first
  if (request.destination === 'style' || request.destination === 'script' || request.destination === 'image') {
      return caches.open(CACHE).match(request).then(cached => cached || fetch(request));
  }
  // Убрать рекурсивный /offline?_sw_ping= — пинговать другим URL
  ```
- **Что проверять:**
  - После logout SW не отдаёт кэшированный `/my-jobs` анониму.
  - В DevTools нет рекурсивных запросов `/offline?_sw_ping=`.

---

### Фаза 4 — Инфраструктура и наблюдаемость

#### Task 4.1 — `Config` как `@dataclass(frozen=True)` с `from_env()` factory
- **Task ID:** `4.1`
- **Что меняется:** `app/config.py:1-93`.
- **Почему:** R-5, R-76. Все вычисляется на import-time; `load_dotenv()` как side-effect; `RuntimeError` в dev если `SECRET_KEY` отсутствует; `SESSION_COOKIE_SECURE` только в production.
- **Как:**
  ```python
  from dataclasses import dataclass, field
  import os

  @dataclass(frozen=True)
  class Config:
      SECRET_KEY: str
      PGRST_JWT_SECRET: str
      POSTGREST_URL: str
      REDIS_URL: str = 'redis://localhost:6379/0'
      SESSION_COOKIE_SECURE: bool = True  # всегда True
      SESSION_COOKIE_HTTPONLY: bool = True
      SESSION_COOKIE_SAMESITE: str = 'Lax'
      PERMANENT_SESSION_LIFETIME: int = 1800
      DEPLOYMENT_ENV: str = 'development'
      MONETIZATION_ENABLED: bool = False  # всегда False в текущем спринте
      ADMIN_API_TOKEN: str = ''
      TESTING: bool = False

      @classmethod
      def from_env(cls) -> 'Config':
          secret = os.environ.get('SECRET_KEY')
          if not secret or len(secret) < 32:
              raise RuntimeError('SECRET_KEY must be set and >= 32 chars')
          pgrst = os.environ.get('PGRST_JWT_SECRET')
          if not pgrst:
              raise RuntimeError('PGRST_JWT_SECRET must be set')
          return cls(
              SECRET_KEY=secret,
              PGRST_JWT_SECRET=pgrst,
              POSTGREST_URL=os.environ.get('POSTGREST_URL', 'http://localhost:3000'),
              # ...
          )

  # В create_app():
  config = Config.from_env()
  app.config.from_object(config)
  ```
- **Что проверять:**
  - Без `SECRET_KEY` приложение падает при старте с понятным сообщением.
  - `SESSION_COOKIE_SECURE=True` даже в dev (cookie не отправляются по HTTP).

#### Task 4.2 — Structlog JSON-логи
- **Task ID:** `4.2`
- **Что меняется:** `app/utils/logging_config.py` — подключить в `create_app()`.
- **Почему:** R-80. Структурированные логи с `request_id`, `user_id` для будущего OpenTelemetry/Sentry.
- **Как:**
  ```python
  import structlog, logging, sys, uuid
  from flask import g, request, session

  def setup_json_logging(app):
      structlog.configure(
          processors=[
              structlog.contextvars.merge_contextvars,
              structlog.processors.add_log_level,
              structlog.processors.TimeStamper(fmt='iso'),
              structlog.processors.JSONRenderer(),
          ],
          wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
          logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
      )

      @app.before_request
      def _bind_request_context():
          g.request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
          structlog.contextvars.bind_contextvars(
              request_id=g.request_id,
              user_id=session.get('user_id'),
              path=request.path,
              method=request.method,
          )
  ```
  Добавить `structlog` в `requirements.txt`.
- **Что проверять:**
  - Логи в stdout — JSON-строки с `request_id`, `user_id`, `path`.
  - `grep "secret\|password" /var/log/app.log` возвращает 0 строк (кроме hash).

#### Task 4.3 — Prometheus `/metrics` endpoint
- **Task ID:** `4.3`
- **Что меняется:** Новый файл `app/blueprints/metrics.py`. Регистрация в `create_app()`.
- **Почему:** R-80. RPS, p50/p95/p99 latency, error rate, CB state — для мониторинга.
- **Как:**
  ```python
  from flask import Blueprint, Response
  from prometheus_client import generate_latest, Counter, Histogram, Gauge

  bp = Blueprint('metrics', __name__)
  REQUEST_COUNT = Counter('flask_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
  REQUEST_LATENCY = Histogram('flask_request_latency_seconds', 'Request latency', ['endpoint'])
  CIRCUIT_BREAKER_STATE = Gauge('postgrest_circuit_breaker_open', '1 if open, 0 if closed')

  @bp.route('/metrics')
  def metrics():
      return Response(generate_latest(), mimetype='text/plain')
  ```
  Endpoint `/metrics` защищён `X-Admin-Token` (как `/health/postgrest`).
- **Что проверять:**
  - `curl http://localhost:5000/metrics` без токена → 403.
  - С токеном — Prometheus-формат.

#### Task 4.4 — Sentry integration
- **Task ID:** `4.4`
- **Что меняется:** `requirements.txt` добавить `sentry-sdk[flask]==2.x`. В `create_app()` инициализировать, если `SENTRY_DSN` в env.
- **Почему:** R-80.
- **Как:**
  ```python
  sentry_dsn = os.environ.get('SENTRY_DSN')
  if sentry_dsn:
      import sentry_sdk
      from sentry_sdk.integrations.flask import FlaskIntegration
      sentry_sdk.init(
          dsn=sentry_dsn,
          integrations=[FlaskIntegration()],
          traces_sample_rate=0.1,
          environment=app.config['DEPLOYMENT_ENV'],
          before_send=_scrub_secrets_from_sentry_event,
      )

  def _scrub_secrets_from_sentry_event(event, hint):
      for key in ('SECRET_KEY', 'PGRST_JWT_SECRET', 'password', 'password_hash'):
          if key in event.get('request', {}).get('data', {}):
              event['request']['data'][key] = '[REDACTED]'
      return event
  ```
- **Что проверять:**
  - Бросок тестовой ошибки → появляется в Sentry.
  - В Sentry event нет `SECRET_KEY` / `password_hash`.

#### Task 4.5 — Security headers
- **Task ID:** `4.5`
- **Что меняется:** `app/__init__.py:170-197` `add_security_headers`. Добавить/усилить: HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
- **Почему:** R-105.
- **Как:**
  ```python
  @app.after_request
  def add_security_headers(resp):
      resp.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
      resp.headers['X-Frame-Options'] = 'DENY'
      resp.headers['X-Content-Type-Options'] = 'nosniff'
      resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
      resp.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
      if 'Content-Security-Policy' not in resp.headers:
          resp.headers['Content-Security-Policy'] = (
              "default-src 'self'; "
              "script-src 'self' 'nonce-{nonce}' 'strict-dynamic'; "
              "style-src 'self' 'unsafe-inline'; "
              "img-src 'self' data: blob: https:; "
              "connect-src 'self' wss: https:; "
              "frame-ancestors 'none'; "
              "upgrade-insecure-requests"
          ).format(nonce=g.csp_nonce)
      return resp
  ```
- **Что проверять:**
  - `curl -I https://trudnik.amvera.io/` показывает все 6 заголовков.
  - securityheaders.com — оценка A или выше.

#### Task 4.6 — Docker hardening
- **Task ID:** `4.6`
- **Что меняется:** `Dockerfile`, `docker-compose.yml`.
- **Почему:** R-6, R-106.
- **Как:**
  - `docker-compose.yml`: PostgreSQL и PostgREST порты привязать к `127.0.0.1:5432` (не `0.0.0.0`).
  - `Dockerfile`: multi-stage build; non-root user (уже есть `appuser`); `--read-only` runtime флаг (кроме `/tmp` и `/app/uploads`).
  - WS-контейнеру передать `PGRST_JWT_SECRET` (после Task 1.7).
  - `.dockerignore`: исключить `.git`, `node_modules`, `tests/`, `tests_e2e/`, `archive/`, `trash/`, `Promts/`.
- **Что проверять:**
  - `docker scan trudnik:latest` (Trivy) — 0 critical CVE.
  - `docker exec ... id` показывает `uid=1000(appuser)`.

#### Task 4.7 — Celery Flower monitoring
- **Task ID:** `4.7`
- **Что меняется:** `requirements.txt` добавить `flower`. `supervisord.conf` добавить process `[program:flower]` на порт 5555 (только `127.0.0.1`).
- **Почему:** R-78.
- **Как:** Прямая правка конфигов.
- **Что проверять:**
  - `curl http://localhost:5555/api/workers` возвращает JSON со статусом воркеров.

#### Task 4.8 — Celery beat: cleanup-old-notifications
- **Task ID:** `4.8`
- **Что меняется:** `app/tasks/celery_app.py:81-103`.
- **Почему:** R-66. `notification_outbox` растёт без очистки.
- **Как:**
  ```python
  beat_schedule = {
      'cleanup-old-notifications': {
          'task': 'app.tasks.maintenance_tasks.cleanup_orphaned_notifications',
          'schedule': crontab(hour=3, minute=0),
      },
      'cleanup-old-email-logs': {
          'task': 'app.tasks.email_tasks.cleanup_old_email_logs',
          'schedule': crontab(hour=4, minute=0),
      },
  }
  ```
- **Что проверять:**
  - В `audit_log` Celery beat появляются записи `cleanup-old-notifications` ежедневно.

#### Task 4.9 — Backup strategy (документация + скрипт)
- **Task ID:** `4.9`
- **Что меняется:** Новый скрипт `scripts/backup_pg.sh` + документация `docs/BACKUP.md`.
- **Почему:** R-103.
- **Как:** Скрипт `pg_dump --format=custom --file=/backups/$(date +%Y%m%d_%H%M%S).dump`; cron; retention 7 daily / 4 weekly / 12 monthly; quarterly restore test — в `docs/BACKUP.md`.
- **Что проверять:**
  - `scripts/backup_pg.sh` запускается вручную, создаёт `.dump` файл.
  - `docs/BACKUP.md` описывает restore procedure.

#### Task 4.10 — Incident response plan + `.well-known/security.txt`
- **Task ID:** `4.10`
- **Что меняется:** Новые файлы `docs/security/irp.md`, `static/.well-known/security.txt`.
- **Почему:** R-104.
- **Как:** Документация: контакт лист, эскалация, шаблон post-mortem. `security.txt` — `Contact:`, `Expires:`, `Preferred-Languages: ru, en`.
- **Что проверять:**
  - `curl https://trudnik.amvera.io/.well-known/security.txt` возвращает текст.

---

### Фаза 5 — Заглушки для будущего биллинга (без реализации)

> **Важно.** В этой фазе создаются **только абстрактные интерфейсы**. Никаких реальных вызовов платёжных провайдеров, никаких `@requires_plan` декораторов с реальным поведением, никаких webhook-эндпоинтов. Заглушки должны быть **no-op** в текущем коде.

#### Task 5.1 — `PaymentGateway` abstract interface
- **Task ID:** `5.1`
- **Что меняется:** Новый файл `app/services/payment_gateway.py`. **Не удалять** `app/services/payment_service.py` (он остаётся как dead code; на него завязаны тесты в `tests/test_all_functions.py:970-982`).
- **Почему:** R-65, R-124. Подготовить почву для будущего биллинга без изменения ядра.
- **Как:**
  ```python
  # app/services/payment_gateway.py
  from abc import ABC, abstractmethod
  from dataclasses import dataclass
  from typing import Optional

  @dataclass
  class PaymentRequest:
      amount: float
      currency: str = 'RUB'
      description: str = ''
      return_url: str = ''
      metadata: dict = None

  @dataclass
  class PaymentResult:
      payment_id: str
      confirmation_url: str
      status: str
      provider: str

  @dataclass
  class WebhookPayload:
      payment_id: str
      status: str
      raw_data: bytes
      signature: str

  class PaymentGateway(ABC):
      """Abstract interface for payment providers.

      Implementations (future, NOT in this sprint):
      - YooKassaPaymentGateway
      - CloudPaymentsPaymentGateway
      - MockPaymentGateway (for tests)
      """

      @abstractmethod
      def create_payment(self, request: PaymentRequest) -> PaymentResult:
          raise NotImplementedError

      @abstractmethod
      def verify_webhook(self, payload: WebhookPayload) -> bool:
          raise NotImplementedError

      @abstractmethod
      def get_payment_status(self, payment_id: str) -> str:
          raise NotImplementedError

      @abstractmethod
      def refund(self, payment_id: str, amount: Optional[float] = None) -> bool:
          raise NotImplementedError


  class NullPaymentGateway(PaymentGateway):
      """No-op implementation. Used while monetization is disabled.

      All methods either return mock values or raise NotImplementedError.
      This is the default gateway injected by the DI container.
      """

      def create_payment(self, request: PaymentRequest) -> PaymentResult:
          raise NotImplementedError('Monetization is disabled; payment gateway not configured')

      def verify_webhook(self, payload: WebhookPayload) -> bool:
          return False  # always reject — no webhooks expected

      def get_payment_status(self, payment_id: str) -> str:
          return 'disabled'

      def refund(self, payment_id: str, amount: Optional[float] = None) -> bool:
          raise NotImplementedError('Monetization is disabled')
  ```
  В `app/container.py` добавить:
  ```python
  from app.services.payment_gateway import NullPaymentGateway

  @dataclass
  class Container:
      # ... existing fields
      payment_gateway: PaymentGateway = field(default_factory=NullPaymentGateway)
  ```
- **Что проверять:**
  - `pytest tests/test_payment_gateway.py` (новый) — `NullPaymentGateway.create_payment` raises `NotImplementedError`.
  - `grep -r "from app.services.payment_gateway" app/` — только в `container.py`.
  - Существующий `payment_service.py` не тронут.

#### Task 5.2 — `SubscriptionService` abstract interface
- **Task ID:** `5.2`
- **Что меняется:** Новый файл `app/services/subscription_service.py`.
- **Почему:** R-123. Подготовить почву для тарифов без реализации.
- **Как:**
  ```python
  # app/services/subscription_service.py
  from abc import ABC, abstractmethod
  from dataclasses import dataclass
  from typing import Optional
  from datetime import datetime

  @dataclass
  class Subscription:
      user_id: str
      plan: str  # 'free', 'basic', 'pro', 'business' (future)
      jobs_remaining: int  # -1 = unlimited
      expires_at: Optional[datetime]
      features: dict

  class SubscriptionService(ABC):
      """Abstract interface for subscription/quota management.

      Implementations (future, NOT in this sprint):
      - DbSubscriptionService (queries employer_subscriptions table)
      - MockSubscriptionService (for tests)

      The DI container injects FreeTierSubscriptionService which always
      returns unlimited quota — preserving current behavior.
      """

      @abstractmethod
      def get_subscription(self, user_id: str) -> Subscription:
          raise NotImplementedError

      @abstractmethod
      def check_quota(self, user_id: str, action: str) -> bool:
          raise NotImplementedError

      @abstractmethod
      def consume_quota(self, user_id: str, action: str) -> None:
          raise NotImplementedError

      @abstractmethod
      def upgrade(self, user_id: str, plan: str, payment_id: str) -> Subscription:
          raise NotImplementedError


  class FreeTierSubscriptionService(SubscriptionService):
      """No-op implementation. All users are on free tier.

      Returns unlimited quota for all actions to preserve existing behavior.
      """

      def get_subscription(self, user_id: str) -> Subscription:
          return Subscription(
              user_id=user_id,
              plan='free',
              jobs_remaining=-1,  # unlimited
              expires_at=None,
              features={'all': True},
          )

      def check_quota(self, user_id: str, action: str) -> bool:
          return True  # always allowed

      def consume_quota(self, user_id: str, action: str) -> None:
          pass  # no-op

      def upgrade(self, user_id: str, plan: str, payment_id: str) -> Subscription:
          raise NotImplementedError('Monetization is disabled')
  ```
  В `app/container.py`:
  ```python
  subscription_service: SubscriptionService = field(default_factory=FreeTierSubscriptionService)
  ```
- **Что проверять:**
  - `pytest tests/test_subscription_service.py` (новый) — `FreeTierSubscriptionService.check_quota` всегда `True`.
  - Существующее поведение `jobs.py:job_new` (quota check при `MONETIZATION_ENABLED=True`) **не меняется** — там остаётся старый inline-код. Только новые Use Cases (Task 2.5) могут опционально использовать `subscription_service.check_quota`.

#### Task 5.3 — `FeatureFlags` service (базовый интерфейс)
- **Task ID:** `5.3`
- **Что меняется:** Новый файл `app/services/feature_flags.py`.
- **Почему:** R-120. Подготовка для plan-gated features и kill switches без реальных платных фич.
- **Как:**
  ```python
  # app/services/feature_flags.py
  from abc import ABC, abstractmethod

  class FeatureFlags(ABC):
      """Abstract interface for feature flags.

      Implementations:
      - RedisFeatureFlags (production, with admin UI to toggle) — future
      - EnvFeatureFlags (per-deployment) — future
      - StaticFeatureFlags (hardcoded — current sprint)
      """

      @abstractmethod
      def is_enabled(self, flag_name: str, user_id: str = None) -> bool:
          raise NotImplementedError

      @abstractmethod
      def enable(self, flag_name: str, user_id: str = None) -> None:
          raise NotImplementedError

      @abstractmethod
      def disable(self, flag_name: str, user_id: str = None) -> None:
          raise NotImplementedError


  class StaticFeatureFlags(FeatureFlags):
      """Static flags from env/config. Used in current sprint.

      All billing-related flags are False by default.
      """

      DEFAULT_FLAGS = {
          'free_tier_active': True,   # приложение работает в бесплатном режиме
          'billing_enabled': False,   # монетизация выключена
          'kkt_enabled': False,       # 54-ФЗ выключен
          'paid_search_boost': False,
          'promoted_jobs': False,
      }

      def __init__(self, overrides: dict = None):
          self._flags = {**self.DEFAULT_FLAGS, **(overrides or {})}

      def is_enabled(self, flag_name: str, user_id: str = None) -> bool:
          return self._flags.get(flag_name, False)

      def enable(self, flag_name: str, user_id: str = None) -> None:
          raise NotImplementedError('StaticFeatureFlags is read-only')

      def disable(self, flag_name: str, user_id: str = None) -> None:
          raise NotImplementedError('StaticFeatureFlags is read-only')
  ```
  В `app/container.py`:
  ```python
  feature_flags: FeatureFlags = field(default_factory=StaticFeatureFlags)
  ```
  В `app/config.py` добавить `FEATURE_FLAGS: dict = field(default_factory=dict)` (переопределения из env).
- **Что проверять:**
  - `pytest tests/test_feature_flags.py` (новый) — `is_enabled('billing_enabled')` всегда `False`.
  - В коде приложения можно использовать `current_app.container.feature_flags.is_enabled('...')` для будущего gating.

#### Task 5.4 — `AuditLogService` (подготовка для billing audit)
- **Task ID:** `5.4`
- **Что меняется:** Новый файл `app/services/audit_log_service.py`.
- **Почему:** R-39, R-41. Подготовка для future billing audit + улучшение текущего admin-audit.
- **Как:**
  ```python
  # app/services/audit_log_service.py
  from dataclasses import dataclass
  from typing import Optional
  from app.utils.postgrest_client import postgrest_admin_request
  import json
  from flask import current_app, session, request

  @dataclass
  class AuditEvent:
      """Structured audit event for any entity mutation."""
      user_id: str          # who performed the action
      action: str           # e.g., 'create_job', 'delete_user', 'payment_succeeded' (future)
      entity_type: str      # 'job', 'profile', 'subscription' (future), 'payment' (future)
      entity_id: str
      old_value: Optional[dict] = None
      new_value: Optional[dict] = None
      ip: Optional[str] = None
      user_agent: Optional[str] = None

  class AuditLogService:
      """Service for writing structured audit events.

      Uses existing `audit_log` table (migration 067). In future, billing
      events (payment_succeeded, subscription_upgraded) will use the same
      table — they should be added to the `action` enum/type when billing is
      wired up, but NOT now.
      """

      def log(self, event: AuditEvent) -> None:
          try:
              postgrest_admin_request('POST', 'audit_log', json={
                  'user_id': event.user_id,
                  'action': event.action,
                  'entity_type': event.entity_type,
                  'entity_id': event.entity_id,
                  'old_value': json.dumps(event.old_value) if event.old_value else None,
                  'new_value': json.dumps(event.new_value) if event.new_value else None,
                  'ip': event.ip,
                  'user_agent': event.user_agent,
              })
          except Exception as e:
              # Audit log is best-effort; never break user flow
              current_app.logger.error('AuditLogService.log failed: %s', e)

      def log_admin_action(self, action: str, entity_type: str, entity_id: str,
                          old_value: dict = None, new_value: dict = None) -> None:
          self.log(AuditEvent(
              user_id=session.get('user_id', 'system'),
              action=action,
              entity_type=entity_type,
              entity_id=entity_id,
              old_value=old_value,
              new_value=new_value,
              ip=request.remote_addr if request else None,
              user_agent=request.headers.get('User-Agent') if request else None,
          ))
  ```
  В `app/container.py`:
  ```python
  audit_log_service: AuditLogService = field(default_factory=AuditLogService)
  ```
  В `app/blueprints/admin.py:log_admin_action` — делегировать в `current_app.container.audit_log_service.log_admin_action(...)`.
- **Что проверять:**
  - `pytest tests/test_audit_log.py` (новый) — `log()` пишет запись в `audit_log` с `user_id` (не `None`).
  - При bulk-delete появляется одна batch-запись с `old_value` = список удалённых ID.

---

### Фаза 6 — Тесты

> **Принцип.** Тесты добавляются параллельно с фазами 0–5. Этот раздел фиксирует минимальный набор.

#### Task 6.1 — Unit-тесты для каждого нового Use Case
- **Task ID:** `6.1`
- **Что меняется:** Новые файлы в `tests/`:
  - `test_apply_job_use_case.py`, `test_withdraw_application_use_case.py`,
    `test_accept_invitation_use_case.py`, `test_create_job_use_case.py`,
    `test_cancel_job_use_case.py`, `test_batch_job_action_use_case.py`
- **Почему:** R-87. Use Cases должны тестироваться без Flask-контекста с fake repositories.
- **Как:**
  ```python
  # tests/test_apply_job_use_case.py
  import pytest
  from app.use_cases.apply_job import ApplyJobUseCase, ApplyJobCommand
  from app.errors import DuplicateApplication, NoSlotsAvailable
  from app.testing.fakes import FakeNotificationService

  class TestApplyJobUseCase:
      def test_successful_apply(self):
          uc = ApplyJobUseCase(notification_service=FakeNotificationService())
          # monkeypatch postgrest_rpc
          ...
          result = uc.execute(ApplyJobCommand(worker_id='w1', job_id='j1'))
          assert result.status == 'pending'

      def test_duplicate_apply_raises(self):
          uc = ApplyJobUseCase(...)
          with pytest.raises(DuplicateApplication):
              uc.execute(ApplyJobCommand(worker_id='w1', job_id='j1'))
  ```
  Создать `app/testing/fakes.py` с fake-репозиториями (заменяют `mock_postgrest.py` постепенно).
- **Что проверять:**
  - `pytest tests/test_apply_job_use_case.py` — все тесты проходят, runtime < 1 с.

#### Task 6.2 — Unit-тесты для каждого нового repository
- **Task ID:** `6.2`
- **Что меняется:** Новые файлы:
  - `test_job_repository.py`, `test_application_repository.py`,
    `test_admin_repository.py`, `test_notification_repository.py`
- **Почему:** R-87.
- **Как:** Использовать `app/testing/mock_postgrest.py` как заглушку PostgREST.
- **Что проверять:**
  - `pytest tests/test_*_repository.py` — все green.

#### Task 6.3 — Unit-тесты для сервисов
- **Task ID:** `6.3`
- **Что меняется:** Новые файлы:
  - `test_storage_service.py`, `test_application_service.py`, `test_job_service.py`,
    `test_invitation_service.py`, `test_ratings_service.py`, `test_circuit_breaker.py`,
    `test_postgrest_client.py`, `test_context_processors.py`, `test_maintenance_tasks.py`,
    `test_payment_gateway.py`, `test_subscription_service.py`, `test_feature_flags.py`,
    `test_audit_log_service.py`
- **Почему:** R-87. Сейчас многие сервисы без unit-тестов.
- **Что проверять:**
  - `pytest --cov=app --cov-report=term-missing` — coverage ≥ 70% для `app/services/`, `app/use_cases/`, `app/repositories/`.

#### Task 6.4 — Integration-тесты на все ~70 роутов
- **Task ID:** `6.4`
- **Что меняется:** Расширить `tests/test_api.py`, `tests/test_new_routes_v2.py`. Для каждого роута: positive, negative, auth/permission (positive + negative), UUID-validation, rate-limit.
- **Почему:** R-88.
- **Как:** Использовать `pytest` + `app.testing.mock_postgrest` для in-memory DB.
- **Что проверять:**
  - `pytest tests/test_api.py` — ≥ 200 тест-кейсов, все green.

#### Task 6.5 — Security-тесты
- **Task ID:** `6.5`
- **Что меняется:** Расширить `tests/test_security.py`, `tests/test_rls.py`. Тесты:
  - SQL-инъекция через все input-поля (parametrized)
  - XSS во всех шаблонах
  - IDOR: user A не может редактировать/удалить сущность user B
  - Path traversal в `/uploads/`
  - Open redirect
  - CSRF на мутирующих эндпоинтах
  - JWT secret не утекает в логи
- **Почему:** R-93.
- **Что проверять:**
  - `pytest tests/test_security.py` — все тесты green.

#### Task 6.6 — Performance-тесты (k6)
- **Task ID:** `6.6`
- **Что меняется:** Новый файл `tests/perf/k6_load.js`. CI-задача `k6 run` на staging.
- **Почему:** R-92.
- **Как:**
  ```javascript
  import http from 'k6/http';
  import { check, sleep } from 'k6';

  export let options = {
      stages: [
          { duration: '30s', target: 100 },
          { duration: '1m', target: 500 },
          { duration: '30s', target: 0 },
      ],
      thresholds: {
          http_req_duration: ['p(95)<500'],
          http_req_failed: ['rate<0.01'],
      },
  };

  export default function () {
      let res = http.get('https://staging.trudnik.amvera.io/');
      check(res, { 'status 200': r => r.status === 200 });
      sleep(1);
  }
  ```
- **Что проверять:**
  - `k6 run tests/perf/k6_load.js` — p95 latency < 500 мс при 500 одновременных.

#### Task 6.7 — GitHub Actions CI
- **Task ID:** `6.7`
- **Что меняется:** Новый файл `.github/workflows/ci.yml`.
- **Почему:** R-94.
- **Как:**
  ```yaml
  name: CI
  on: [push, pull_request]
  jobs:
    lint:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: '3.12' }
        - run: pip install black isort flake8 mypy bandit
        - run: black --check app/ tests/
        - run: isort --check app/ tests/
        - run: flake8 app/ tests/
        - run: mypy app/
        - run: bandit -r app/ -ll
    test:
      runs-on: ubuntu-latest
      services:
        redis: { image: redis:7-alpine, ports: ['6379:6379'] }
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: '3.12' }
        - run: pip install -r requirements.txt -r requirements-dev.txt
        - run: pytest --cov=app --cov-report=xml --cov-fail-under=70
        - uses: codecov/codecov-action@v4
    security:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: pip install pip-audit
        - run: pip-audit -r requirements.txt
  ```
- **Что проверять:**
  - PR не мержится, если `lint` / `test` / `security` падают.

---

## 4. Несоответствия между рекомендациями Plan и реальным кодом (ШАГ 4)

> Если в процессе анализа найдено несоответствие между рекомендацией и реальностью — рекомендация **не применяется**, а фиксируется здесь с объяснением.

### 4.1 Несоответствия, НЕ подлежащие исправлению в текущем спринте (биллинг-зона)

| # | Рекомендация | Реальность | Решение |
|---|---|---|---|
| N-1 | R-65: исправить `payment_service.verify_webhook` (`hexdigest` → base64) | Файл `app/services/payment_service.py` — **dead code**. Ни один метод не вызывается из blueprint'ов. Нет webhook-эндпоинта. | НЕ ИСПРАВЛЯТЬ в текущем спринте. Создать абстрактный `PaymentGateway` (Task 5.1) с `NullPaymentGateway` как no-op. Реальную реализацию YooKassa с правильным base64 — когда начнётся биллинг-спринт. Существующий `payment_service.py` НЕ ТРОГАТЬ (на него завязаны тесты). |
| N-2 | R-83: распространять `tariff`/`is_paid`/`promoted_until`/`is_promoted` через create/edit/copy/duplicate flows | Это сама логика монетизации. | ОТЛОЖИТЬ. Все 8 битых мест задокументированы в §2.2 (R-123). НЕ исправлять. |
| N-3 | R-82 (часть): `migrations/067:197, 451` — `tariff varchar(20) DEFAULT 'standard'` vs `employer_subscriptions` CHECK `('basic','pro','business')` | CHECK-ограничение конфликтует с DEFAULT-значением. INSERT с default всегда упадёт. | НЕ ТРОГАТЬ в текущем спринте. Изменение CHECK требует миграции, которая может затронуть будущий биллинг-дизайн. Задокументировать как `TODO(billing)` в комментарии к `employer_subscriptions` модели. |
| N-4 | R-123: `app/blueprints/auth.py:366-418` — регистрация работодателя не создаёт запись в `employer_subscriptions` | Это будущая зона биллинга. | НЕ ИСПРАВЛЯТЬ. Когда биллинг будет включён, `FreeTierSubscriptionService.get_subscription()` будет создаваться по умолчанию. Сейчас `FreeTierSubscriptionService` возвращает hard-coded free-tier без БД-записи. |
| N-5 | R-123: `app/blueprints/jobs.py:449-469` — quota check только при `MONETIZATION_ENABLED=True`, но creation никогда не пишет `is_paid` | Логика монетизации. | НЕ ИСПРАВЛЯТЬ. `MONETIZATION_ENABLED=False` по умолчанию (Task 4.1), поэтому quota check не выполняется. Когда биллинг включат — нужно будет вызывать `subscription_service.consume_quota()` в `CreateJobUseCase` (Task 2.5). |
| N-6 | R-84: `worker_contacts` отдаёт email безусловно; `employer_detail`/`public_profile` показывают phone без verification | Гейтинг по подписке — будущая зона. | НЕ ИСПРАВЛЯТЬ сейчас. Однако в §3 Task 1.21 добавляется role-check для `verify_employer` — это базовая защита, не связанная с подпиской. |
| N-7 | R-123: `app/utils/business.py:7-34` `copy_job` копирует `is_paid=False`, но не `expires_at`/`is_promoted`/`promoted_until` | Логика монетизации. | НЕ ИСПРАВЛЯТЬ. Когда биллинг включат, `copy_job` должен будет вызывать `subscription_service.check_quota()` и сбрасывать все платные поля. |
| N-8 | R-62 (часть): `email_service._check_daily_limit` race-condition | Если email-лимиты станут платными (тарифные планы с разными лимитами), это биллинг. | Атомарный `INCR` в Redis можно сделать сейчас (это не биллинг, это rate-limiting). Включено в Task 2.11 как часть SMTP-fix. |

### 4.2 Несоответствия, которые ИСПРАВЛЯЮТСЯ в текущем спринте (не-биллинг)

| # | Рекомендация | Реальность | Решение | Task |
|---|---|---|---|---|
| M-1 | R-66: `notification_service.py:99-105` `base_payload` не содержит `title` (NOT NULL column) | INSERT fails — notification flow сломан. | Добавить `title` в `base_payload`. Это bugfix, не биллинг. | Task 2.8 |
| M-2 | R-66: `email_tasks.py:24, 89` `notification_id: int` (а в БД UUID) | Type mismatch. | Заменить `int` на `str`. Bugfix. | Task 2.8 |
| M-3 | R-66: `notification_service.py:161-172` запрашивает несуществующую колонку `username` | 500 ошибка. | Использовать `full_name`. Bugfix. | Task 2.8 |
| M-4 | SEC-6: `email_service.py:114` `_time_module.timedelta(days=1)` — AttributeError | Daily-limit counter падает при первом инкременте. | Заменить на `datetime.timedelta`. Bugfix. | Task 1.20 |
| M-5 | SEC-7: `auth.py:551-562` импортирует `send_email` как модульную функцию (а это метод класса) | Password-reset email flow сломан. | Исправить импорт. Bugfix. | Task 1.20 |
| M-6 | R-77: две реализации `rate_limit` (in-memory + Redis) | `app/utils/__init__.py:133` реэкспортирует устаревшую in-memory версию. | Удалить `app/utils/rate_limit.py`; оставить каноничную `app/decorators.py:rate_limit`. | Task 0.4 |
| M-7 | R-77: две реализации `_redis_cache_get/_set/_delete` | Дублирование. | Вынести в `app/cache.py`. | Task 0.1 |
| M-8 | R-77: две копии `_SQL_INJECTION_PATTERNS` | Дублирование. | Удалить legacy-копии. | Task 0.4 |
| M-9 | R-72: `app = create_app()` на уровне модуля | Блокирует `gunicorn --preload`. | Удалить; вызывать явно в `app.py`. | Task 0.2 |
| M-10 | R-77: god-module `app/utils/__init__.py` | Медленный collect-time тестов. | Декомпозировать. | Task 0.5 |

### 4.3 Рекомендации, отклонённые из-за несоответствия стеку

| # | Рекомендация | Причина отклонения |
|---|---|---|
| X-1 | "Внедрить SQLAlchemy 2" (из Trudnik_Flask_Architecture_Audit.md §6, как Could) | Приложение использует PostgREST (HTTP API), не ORM. Внедрение SQLAlchemy = полная перестройка DB-слоя. Architecture Audit сам рекомендует **НЕ внедрять** SQLAlchemy 2. |
| X-2 | "Flask-Smorest/APIFlask для всех роутов" | Только для новых `/api/*` роутов. Существующие HTML-роуты — Jinja2. |
| X-3 | "Перейти на Playwright, заменить Selenium" (R-89) | В `tests/` уже есть `test_selenium_browser.py`, `test_selenium_v2.py`. В `tests_e2e/` — Playwright-стиль. Полная замена = переписывание 21k LOC тестов. Откладывается. |
| X-4 | "Полный design system + Storybook" (R-107) | UI-изменения запрещены ограничениями задания. |
| X-5 | "152-ФЗ compliance: consent checkbox, public Privacy Policy, Roskomnadzor notification" (R-97) | Юридическая работа; вне рамок технического рефакторинга. Подготовить технические предпосылки (audit log) — можно (Task 5.4). |
| X-6 | "54-ФЗ KKT интеграция" (R-98) | Биллинг. Откладывается. |
| X-7 | "GDPR DSAR workflow" (R-100) | Только если планируются EU-пользователи. |
| X-8 | "Admin RBAC: 3 роли (super_admin/moderator/editor) + IP-whitelist" (R-39) | Полная перестройка admin-RBAC. Текущий одиночный `admin` достаточен для бесплатной версии. |
| X-9 | "WebAuthn для админов" (R-21) | Оверкилл для текущей стадии. |
| X-10 | "Full-text search via tsvector + GIN" (R-117) | Большая миграция; не приоритет. Может быть добавлена как аддитивный индекс позже. |

---

## 5. Критерии приёмки (ШАГ 5)

После выполнения всех задач плана приложение должно соответствовать следующим критериям.

### 5.1 Сборка и запуск
- [ ] `docker compose build` проходит без ошибок.
- [ ] `docker compose up` поднимает все сервисы (postgres, postgrest, redis, web, celery worker, celery beat, websocket, flower).
- [ ] `gunicorn --preload -w 4 'app:create_app()'` запускается (раньше падал из-за `app = create_app()` на уровне модуля).
- [ ] `import app` не делает HTTP-запросов и не блокирует > 1 с.
- [ ] Без `SECRET_KEY` или `PGRST_JWT_SECRET` в env приложение падает при старте с понятной ошибкой.

### 5.2 Безопасность
- [ ] `grep -r "secret\[:8\]\|secret\[:16\]\|PGRST_JWT_SECRET\[:.*\]" app/` возвращает 0 строк.
- [ ] `grep -r "dev-secret-change-me\|fallback-secret-key" app/ websocket_server/` возвращает 0 строк.
- [ ] `pytest tests/test_security.py` — все тесты green, включая новые: SQL-инъекция, XSS, IDOR, path-traversal, open-redirect, CSRF.
- [ ] `bandit -r app/ -ll` — 0 high-severity находок.
- [ ] `pip-audit -r requirements.txt` — 0 critical CVE.
- [ ] В логах приложения (structlog JSON) нет `password`, `secret`, `password_hash`.
- [ ] `curl -I https://trudnik.amvera.io/` показывает: HSTS, X-Frame-Options: DENY, X-Content-Type-Options: nosniff, Referrer-Policy, Permissions-Policy, Content-Security-Policy.
- [ ] `/health/postgrest` без `X-Admin-Token` → 403.
- [ ] `/uploads/verification/<file>` без auth → 401.
- [ ] После logout старый JWT возвращает 401 на PostgREST-запросах.

### 5.3 Производительность
- [ ] `/admin` dashboard грузится < 100 мс (раньше 500–800 мс).
- [ ] `/job/<id>` делает 1 PostgREST-запрос (раньше — 5+).
- [ ] `/` (залогиненный пользователь) — 1 PostgREST-запрос на counters (раньше — 3+ на каждый рендер).
- [ ] `k6 run tests/perf/k6_load.js` — p95 latency < 500 мс при 500 одновременных.
- [ ] `grep -r "threading.Thread" app/blueprints/` возвращает 0 строк.
- [ ] `grep -r "_apply_job_fallback" app/` возвращает 0 строк.
- [ ] `grep -r "subprocess.check_output.*git" app/blueprints/` возвращает 0 строк.
- [ ] JWT в session переиспользуется 4 минуты (логи Redis: `SETEX pgrst_jti:*` — 1 раз в 4 мин, не на каждый запрос).

### 5.4 Архитектура
- [ ] Существуют файлы: `app/cache.py`, `app/errors.py`, `app/error_handlers.py`, `app/container.py`, `app/repositories/` (4 файла), `app/use_cases/` (5+ файлов).
- [ ] `app/services/payment_gateway.py` содержит `PaymentGateway` ABC + `NullPaymentGateway`.
- [ ] `app/services/subscription_service.py` содержит `SubscriptionService` ABC + `FreeTierSubscriptionService`.
- [ ] `app/services/feature_flags.py` содержит `FeatureFlags` ABC + `StaticFeatureFlags` (с `billing_enabled=False`).
- [ ] `app/services/audit_log_service.py` содержит `AuditLogService` + `AuditEvent` dataclass.
- [ ] `app/container.py` регистрирует все репозитории, сервисы, use cases.
- [ ] `current_app.container.apply_job_use_case().execute(cmd)` работает.
- [ ] Миграции `076_get_admin_stats.sql`, `077_notifications_entity_columns.sql` применены без ошибок.
- [ ] Ни одна миграция не содержит `DROP COLUMN` / `RENAME` / изменения `CHECK` на `tariff`/`is_paid`.

### 5.5 Бизнес-логика (без изменений)
- [ ] Регистрация worker/employer работает как прежде.
- [ ] Login/logout работает (logout теперь блэклистит JWT + чистит SW).
- [ ] Create/edit/delete vacancy работает.
- [ ] Apply/withdraw/accept/reject заявки работает.
- [ ] Чат между employer ↔ worker работает.
- [ ] Уведомления (in-app, email, push) работают.
- [ ] Ratings/reviews работают.
- [ ] Admin panel (просмотр, bulk-delete, manage skills/religions) работает.
- [ ] `MONETIZATION_ENABLED=False` (по умолчанию). Все пользователи — free tier. Никаких платных фич не появилось.
- [ ] Существующий `app/services/payment_service.py` НЕ ТРОНУТ.
- [ ] Существующие биллинг-хуки (`tariff`/`is_paid`/`employer_subscriptions`) НЕ ИСПРАВЛЕНЫ (см. §4.1).

### 5.6 Тестирование
- [ ] `pytest tests/` — все тесты green.
- [ ] `pytest --cov=app --cov-fail-under=70` — проходит.
- [ ] `pytest tests/test_apply_job_use_case.py` — Use Case тестируется без Flask-контекста.
- [ ] `pytest tests/test_payment_gateway.py` — `NullPaymentGateway.create_payment` raises `NotImplementedError`.
- [ ] `pytest tests/test_subscription_service.py` — `FreeTierSubscriptionService.check_quota` всегда `True`.
- [ ] `pytest tests/test_feature_flags.py` — `is_enabled('billing_enabled')` всегда `False`.
- [ ] GitHub Actions CI: lint + test + security — все green на PR.

### 5.7 Наблюдаемость
- [ ] `/metrics` (Prometheus) возвращает метрики (с `X-Admin-Token`).
- [ ] Логи в stdout — JSON-строки с `request_id`, `user_id`, `path`.
- [ ] Sentry получает тестовую ошибку (если `SENTRY_DSN` задан).
- [ ] Flower UI доступен на `http://localhost:5555`.
- [ ] `curl https://trudnik.amvera.io/.well-known/security.txt` возвращает текст.

---

## 6. Промт для следующего агента (исполнитель)

> **Скопируй текст ниже и передай его следующему агенту-разработчику.**

---

### РОЛЬ И КОНТЕКСТ

Ты — senior Python/Flask разработчик. Твоя задача — выполнить рефакторинг приложения **trudnik** в соответствии с `EXECUTION_PLAN.md`. Документ находится в `/home/z/my-project/download/EXECUTION_PLAN.md`.

### ВХОДНЫЕ ДАННЫЕ

- **Исходный код:** `/home/z/my-project/work/trudnik/trudnik/` (Flask + PostgREST + Redis + Celery + WebSocket).
- **План:** `/home/z/my-project/download/EXECUTION_PLAN.md` — пошаговое задание с Task ID, файлами, обоснованиями и кодом.
- **Worklog:** `/home/z/my-project/worklog.md` — после каждой задачи добавляй запись (см. формат ниже).

### ЖЁСТКИЕ ОГРАНИЧЕНИЯ (читай перед каждым действием)

1. **Не читать** папки `archive/`, `trash/`, `Promts/` внутри `trudnik/`.
2. **Не внедрять монетизацию**: никаких реальных платёжных провайдеров, никаких `@requires_plan` с реальным поведением, никаких webhook-эндпоинтов. Только абстрактные интерфейсы-заглушки (Phase 5).
3. **Не менять UI** без необходимости. Допускается: XSS-fix'ы (`|e` фильтры), `loading="lazy"`, минимальная пагинация UI, исправление SW-багов.
4. **Не удалять и не переименовывать сущности БД**. Миграции — только аддитивные (`CREATE INDEX`, `CREATE FUNCTION`, `ALTER TABLE ... ADD COLUMN`).
5. **Не исправлять "битые хуки" биллинга** — они задокументированы в §4.1 плана. Если видишь несоответствие между `tariff='standard'` и CHECK `('basic','pro','business')` — НЕ ТРОГАТЬ.
6. **Не удалять** `app/services/payment_service.py` (он dead code, но на него завязаны тесты в `tests/test_all_functions.py:970-982`).
7. **Все скрипты рефакторинга** сохраняй в `/home/z/my-project/scripts/refactor/<task_id>.py` (или в репозитории в `scripts/refactor/`).
8. **Обратная совместимость сессий**: после изменений залогиненный пользователь не должен разлогиниваться.

### ДИАГНОСТИКА (кратко, из §1 плана)

- **Стек:** Flask 3.1.3 + PostgREST v12.2.3 (HTTP API, без ORM) + Redis 7 + Celery 5.6.3 + FastAPI WebSocket + Tailwind/Jinja2.
- **Архитектура:** 14 blueprint'ов + 9 сервисов + 12 utils + 3 Celery-task-модуля.
- **Критичные уязвимости:** SEC-1..SEC-32 (см. §1.4 плана). Самые серьёзные — логирование префикса JWT-секрета (SEC-1, SEC-2), broken WS-аутентификация (SEC-13..SEC-16), dead-code `payment_service.py` (SEC-3).
- **Узкие места:** BN-1..BN-15 (см. §1.3 плана). Главное — admin-dashboard (8 seq. запросов), `role_required` per-request PostgREST-call, `cache_for` in-memory, `app = create_app()` на уровне модуля.

### ПОРЯДОК ВЫПОЛНЕНИЯ

Выполняй задачи строго по фазам. Внутри фазы — по Task ID. После каждой задачи:

1. Запусти соответствующие тесты (см. "Что проверять" в каждой задаче).
2. Если тесты проходят — добавь запись в `/home/z/my-project/worklog.md`:
   ```
   ---
   Task ID: <X.Y>
   Agent: <твоё имя/роль>
   Task: <краткое описание>

   Work Log:
   - <шаг 1>
   - <шаг 2>
   - ...

   Stage Summary:
   - <артефакты>
   - <результаты тестов>
   - <отклонения от плана (если есть)>
   ```
3. Если тесты падают — откатись через `git checkout -- <files>` (или эквивалент) и попробуй другой подход. Не коммить сломанный код.
4. Коммить после каждой успешно выполненной задачи (commit message: `refactor(task-X.Y): <title>`).

### ФАЗЫ И ЗАДАЧИ

| Фаза | Кол-во задач | Описание |
|---|---|---|
| 0 | 5 | Утилиты и хелперы (вынести `app/cache.py`, убрать global app, декомпозировать utils) |
| 1 | 22 | Критичные security hot-fixes (JWT secret logging, WS auth, XSS, CSRF, ownership checks) |
| 2 | 14 | Ядро бизнес-логики (errors, repositories, use cases, DI container, cache_for на Redis) |
| 3 | 14 | API и роуты (admin stats RPC, role_required cache, job_detail embedded, pagination) |
| 4 | 10 | Инфраструктура (Config dataclass, structlog, Prometheus, Sentry, security headers, Docker hardening) |
| 5 | 4 | Заглушки для биллинга (PaymentGateway, SubscriptionService, FeatureFlags, AuditLogService) |
| 6 | 7 | Тесты (unit, integration, security, performance, CI) |

**Итого: 76 задач.**

### КРИТЕРИИ ПРИЁМКИ (см. §5 плана)

- Приложение собирается: `docker compose build` без ошибок.
- `gunicorn --preload -w 4 'app:create_app()'` запускается.
- `pytest tests/` — все green.
- `pytest --cov=app --cov-fail-under=70` — проходит.
- `bandit -r app/ -ll` — 0 high-severity.
- `grep -r "threading.Thread" app/blueprints/` — 0 строк.
- `grep -r "_apply_job_fallback" app/` — 0 строк.
- `grep -r "secret\[:8\]\|secret\[:16\]" app/` — 0 строк.
- Существуют: `app/cache.py`, `app/errors.py`, `app/container.py`, `app/repositories/`, `app/use_cases/`, `app/services/payment_gateway.py`, `app/services/subscription_service.py`, `app/services/feature_flags.py`, `app/services/audit_log_service.py`.
- `MONETIZATION_ENABLED=False`. Все пользователи — free tier. `payment_service.py` НЕ ТРОНУТ.
- Биллинг-хуки (§4.1 плана) НЕ ИСПРАВЛЕНЫ.
- Все миграции аддитивные (нет `DROP COLUMN` / `RENAME`).

### ЕСЛИ ВСТРЕТИЛ НЕСОТВЕТСТВИЕ ПЛАНУ

Если в процессе выполнения ты находишь, что план описывает файл/функцию, которой нет в реальности, или наоборот — НЕ модифицируй план. Добавь запись в `/home/z/my-project/worklog.md`:
```
DEVIATION (Task X.Y):
- Plan says: <цитата>
- Reality: <что нашёл>
- Decision: <что сделал вместо этого>
```

### ФИНАЛЬНЫЙ ОТЧЁТ

После завершения всех задач (или при остановке) — добавь в `/home/z/my-project/worklog.md` секцию:
```
---
Task ID: FINAL
Agent: <твоё имя>
Task: Финальный отчёт

Work Log:
- Выполнено задач: <N>/76
- Пропущено: <список Task ID + причина>
- Отклонений от плана: <N>

Stage Summary:
- Приложение собирается: yes/no
- pytest проходит: yes/no (X failed, Y passed)
- coverage: X%
- Критичные remaining issues: <список>
```

**Приступай к Task 0.1. Удачи.**

---

## Приложение A. Сводная таблица Task ID → Рекомендации Plan

| Task ID | R-ID из Plan | Категория | Фаза |
|---|---|---|---|
| 0.1 | R-71, R-77 | refactor | 0 |
| 0.2 | R-54, R-71 | refactor | 0 |
| 0.3 | R-54 | perf | 0 |
| 0.4 | R-77 | refactor | 0 |
| 0.5 | R-77 | refactor | 0 |
| 1.1 | R-2 | security | 1 |
| 1.2 | R-1 (часть) | security | 1 |
| 1.3 | R-3 | security | 1 |
| 1.4 | R-40 | security | 1 |
| 1.5 | R-36 | security | 1 |
| 1.6 | R-9 | security | 1 |
| 1.7 | R-16, R-17, R-18, R-19 | security | 1 |
| 1.8 | R-10, R-11 | security | 1 |
| 1.9 | R-23 | security | 1 |
| 1.10 | R-25 | security | 1 |
| 1.11 | R-27, R-28 | security | 1 |
| 1.12 | R-30 | security | 1 |
| 1.13 | R-31, R-32 | security | 1 |
| 1.14 | R-33 | security | 1 |
| 1.15 | R-37, R-38 | security | 1 |
| 1.16 | R-4 | security | 1 |
| 1.17 | R-41 | security | 1 |
| 1.18 | R-26 | security | 1 |
| 1.19 | R-14 | security | 1 |
| 1.20 | (новое, SEC-6, SEC-7) | security | 1 |
| 1.21 | R-69 | security | 1 |
| 1.22 | R-34 | refactor | 1 |
| 2.1 | R-63, R-72 | refactor | 2 |
| 2.2 | R-63, R-72 | refactor | 2 |
| 2.3 | R-73 | refactor | 2 |
| 2.4 | R-42, R-73 | perf | 2 |
| 2.5 | R-58, R-59, R-74 | refactor | 2 |
| 2.6 | R-76 | refactor | 2 |
| 2.7 | R-66 | refactor | 2 |
| 2.8 | R-66 | refactor | 2 |
| 2.9 | R-58 | refactor | 2 |
| 2.10 | R-49, R-75 | perf | 2 |
| 2.11 | R-50 | perf | 2 |
| 2.12 | R-51 | perf | 2 |
| 2.13 | R-52 | perf | 2 |
| 2.14 | R-53 | perf | 2 |
| 3.1 | R-42 | perf | 3 |
| 3.2 | R-43 | perf | 3 |
| 3.3 | R-46 | perf | 3 |
| 3.4 | R-44 | perf | 3 |
| 3.5 | R-45 | perf | 3 |
| 3.6 | R-60 | refactor | 3 |
| 3.7 | R-47 | perf | 3 |
| 3.8 | R-55 | perf | 3 |
| 3.9 | (новое, SEC-21) | security | 3 |
| 3.10 | R-7 | perf | 3 |
| 3.11 | R-48 | perf | 3 |
| 3.12 | R-67, R-68 | refactor | 3 |
| 3.13 | R-64 | refactor | 3 |
| 3.14 | R-57 | security | 3 |
| 4.1 | R-5, R-76 | refactor | 4 |
| 4.2 | R-80 | monitoring | 4 |
| 4.3 | R-80 | monitoring | 4 |
| 4.4 | R-80 | monitoring | 4 |
| 4.5 | R-105 | security | 4 |
| 4.6 | R-6, R-106 | security | 4 |
| 4.7 | R-78 | monitoring | 4 |
| 4.8 | R-66 | refactor | 4 |
| 4.9 | R-103 | monitoring | 4 |
| 4.10 | R-104 | monitoring | 4 |
| 5.1 | R-65, R-124 (future) | billing-prep | 5 |
| 5.2 | R-123 (future) | billing-prep | 5 |
| 5.3 | R-120 (future) | billing-prep | 5 |
| 5.4 | R-39, R-41 (future) | billing-prep | 5 |
| 6.1 | R-87 | testing | 6 |
| 6.2 | R-87 | testing | 6 |
| 6.3 | R-87 | testing | 6 |
| 6.4 | R-88 | testing | 6 |
| 6.5 | R-93 | testing | 6 |
| 6.6 | R-92 | testing | 6 |
| 6.7 | R-94 | testing | 6 |

---

## Приложение B. Список файлов, которые будут затронуты

### Новые файлы (создаются)
- `app/cache.py`
- `app/errors.py`
- `app/error_handlers.py`
- `app/container.py`
- `app/repositories/__init__.py`
- `app/repositories/base.py`
- `app/repositories/job_repository.py`
- `app/repositories/application_repository.py`
- `app/repositories/admin_repository.py`
- `app/repositories/notification_repository.py`
- `app/use_cases/__init__.py`
- `app/use_cases/apply_job.py`
- `app/use_cases/withdraw_application.py`
- `app/use_cases/accept_invitation.py`
- `app/use_cases/create_job.py`
- `app/use_cases/cancel_job.py`
- `app/use_cases/batch_job_action.py`
- `app/services/payment_gateway.py` (interface + NullPaymentGateway)
- `app/services/subscription_service.py` (interface + FreeTierSubscriptionService)
- `app/services/feature_flags.py` (interface + StaticFeatureFlags)
- `app/services/audit_log_service.py`
- `app/blueprints/metrics.py`
- `app/testing/fakes.py` (fake repositories для тестов)
- `migrations/076_get_admin_stats.sql` (аддитивный)
- `migrations/077_notifications_entity_columns.sql` (аддитивный)
- `tests/test_apply_job_use_case.py` + 5 других use-case тестов
- `tests/test_*_repository.py` (4 файла)
- `tests/test_storage_service.py`, `test_circuit_breaker.py`, `test_postgrest_client.py`, `test_context_processors.py`, `test_maintenance_tasks.py`, `test_payment_gateway.py`, `test_subscription_service.py`, `test_feature_flags.py`, `test_audit_log_service.py`
- `tests/perf/k6_load.js`
- `.github/workflows/ci.yml`
- `scripts/backup_pg.sh`
- `docs/BACKUP.md`
- `docs/security/irp.md`
- `static/.well-known/security.txt`

### Существующие файлы, которые модифицируются
- `app/__init__.py` (убрать global app, _wait_for_postgrest, добавить error_handlers, metrics, security headers, контейнер)
- `app/config.py` (dataclass + from_env factory)
- `app/utils/auth.py` (убрать JWT-secret logging, jti blacklist на refresh)
- `app/utils/postgrest_client.py` (cache_for на Redis, thread-safe Session, CB 5xx-only, JWT в session)
- `app/utils/security.py` (sanitize_postgrest расширить для email)
- `app/utils/rate_limit.py` (удалить — заменён на decorators.rate_limit)
- `app/utils/__init__.py` (декомпозировать)
- `app/utils/helpers.py` (safe_redirect)
- `app/utils/logging_config.py` (structlog)
- `app/decorators.py` (role_required cache, rate_limit Redis sliding-window, decorator order)
- `app/context_processors.py` (WS-JWT 15min TTL, batched counters)
- `app/blueprints/auth.py` (logout jti blacklist, password-reset email fix, sanitize_postgrest, validate_uuid)
- `app/blueprints/profile.py` (MAX_LENGTHS, ownership checks, password confirmation, role-check verify_employer)
- `app/blueprints/jobs.py` (job_detail embedded, delete_job RPC, my_jobs select, my_jobs_action Use Case, job_new error messages, SW fix)
- `app/blueprints/jobs_api.py` (login_required, validate_uuid)
- `app/blueprints/applications.py` (role_required worker, validate_uuid, Use Cases, убрать threading.Thread)
- `app/blueprints/admin.py` (AdminRepository.get_stats, admin search charset, password_hash убрать из select, git-version cached, audit_log во bulk-actions, fix_permissions rate-limit)
- `app/blueprints/ratings.py` (агрегация, login_required)
- `app/blueprints/notifications.py` (login_required, entity_type columns вместо ilike)
- `app/blueprints/employers.py` (validate_uuid, safe_redirect)
- `app/blueprints/favorites.py` (validate_uuid, safe_redirect)
- `app/blueprints/blacklist.py` (validate_uuid, safe_redirect)
- `app/blueprints/chat.py` (UUID validation, content length, cursor pagination)
- `app/services/notification_service.py` (декомпозиция create, title column, NOTIFICATION_TYPES, entity_type)
- `app/services/email_service.py` (datetime.timedelta fix, per-process SMTP, autoescape, env-gate SECRET_KEY)
- `app/services/job_service.py` (enrich_job embedded resources)
- `app/services/storage_service.py` (MIME sniffing, whitelist)
- `app/tasks/celery_app.py` (beat cleanup tasks)
- `app/tasks/email_tasks.py` (notification_id: str)
- `app/tasks/maintenance_tasks.py` (cleanup-old-notifications)
- `app.py` (явный create_app())
- `asgi.py` (явный create_app())
- `websocket_server/auth.py` (PGRST_JWT_SECRET, sub claim, no fallback)
- `websocket_server/main.py` (no wildcard CORS, no token in URL, multi-tab connections)
- `static/sw.js` (no HTML/API cache, fix /offline?_sw_ping=, skipWaiting on logout)
- `templates/base.html` (CSRF fix, SW reload on logout, fetch /api/ws-token)
- `templates/job_detail.html` (XSS fix |e)
- `templates/admin.html` (XSS fix |e)
- `templates/_filter_skills.html` (XSS fix |e)
- `templates/error.html` (custom error pages с support_id)
- `templates/chat.html` (pagination UI)
- `templates/my_applications.html` (pagination UI)
- `templates/workers.html` (pagination UI)
- `templates/my_jobs.html` (POST вместо GET на мутирующих действиях)
- `templates/job_detail.html` (POST вместо GET на cancel/restore/delete)
- `Dockerfile` (multi-stage, non-root, .dockerignore)
- `docker-compose.yml` (127.0.0.1 ports, PGRST_JWT_SECRET в WS)
- `supervisord.conf` (flower process)
- `requirements.txt` (structlog, prometheus-client, sentry-sdk, flower, tenacity)
- `requirements-dev.txt` (pip-audit, bandit, black, isort, flake8, mypy)
- `pytest.ini` (coverage config)
- `.gitignore` (если .env ещё там нет)
- `.env.example` (добавить ADMIN_API_TOKEN, SENTRY_DSN, FEATURE_FLAGS*)

### Файлы, которые НЕ ТРОГАЮТСЯ (важно)
- `app/services/payment_service.py` (dead code, но завязаны тесты)
- `migrations/067_bootstrap_amvera.sql` (уже применён; изменения через новые миграции)
- `migrations/archive/*` (запрещены к чтению)
- `archive/*`, `trash/*`, `Promts/*` (запрещены к чтению)
- Любой файл с `tariff`/`is_paid`/`employer_subscriptions` логикой (биллинг-хуки)
- Любой CHECK-ограничением в БД на `tariff`

---

**Конец документа.**

