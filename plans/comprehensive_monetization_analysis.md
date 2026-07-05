# Комплексный анализ рекомендаций по улучшению приложения Trudnik с учётом будущей монетизации

**Дата:** 2026-06-29
**Версия документа:** 1.0
**Проанализировано файлов:** 16
**Всего извлечено рекомендаций:** ~280

---

## Оглавление

1. [Сводка проанализированных файлов](#1-сводка-проанализированных-файлов)
2. [Систематизированные рекомендации по тематикам](#2-систематизированные-рекомендации-по-тематикам)
   - [2.1 Архитектура](#21-архитектура)
   - [2.2 Безопасность](#22-безопасность)
   - [2.3 Производительность](#23-производительность)
   - [2.4 Пользовательский опыт (UX)](#24-пользовательский-опыт-ux)
   - [2.5 Монетизация](#25-монетизация)
   - [2.6 Тестирование](#26-тестирование)
   - [2.7 Документация](#27-документация)
   - [2.8 Инфраструктура и DevOps](#28-инфраструктура-и-devops)
   - [2.9 Кодовая база и рефакторинг](#29-кодовая-база-и-рефакторинг)
   - [2.10 База данных и миграции](#210-база-данных-и-миграции)
3. [Приоритизация: Внедрить / Отложить / Отклонить](#3-приоритизация-внедрить--отложить--отклонить)
4. [Трёхфазный план реализации](#4-трёхфазный-план-реализации)
5. [План поддержки монетизации](#5-план-поддержки-монетизации)

---

## 1. Сводка проанализированных файлов

| # | Файл | Статус | Объём | Кол-во рекомендаций |
|---|------|--------|-------|---------------------|
| 1 | [`trudnik_fix_prompt.md`](trudnik_fix_prompt.md) | ✅ Прочитан (секции 1-600) | 83 KB | ~28 |
| 2 | [`archive/CODE_REVIEW_FINAL_REPORT.md`](archive/CODE_REVIEW_FINAL_REPORT.md) | ✅ Прочитан (секции 1-400) | 31 KB | ~55+ |
| 3 | [`archive/CODE_REVIEW_CONTEXT.md`](archive/CODE_REVIEW_CONTEXT.md) | ✅ Прочитан (секции 1-400) | 32 KB | ~30+ |
| 4 | [`archive/TESTS_NEW_ARCH.md`](archive/TESTS_NEW_ARCH.md) | ✅ Прочитан (секции 1-400) | 23 KB | ~40+ |
| 5 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | ✅ Прочитан (секции 1-400) | 20 KB | ~10 |
| 6 | [`docs/SECURITY.md`](docs/SECURITY.md) | ✅ Прочитан полностью | 15 KB | ~10 |
| 7 | [`docs/BUSINESS_LOGIC.md`](docs/BUSINESS_LOGIC.md) | ✅ Прочитан (секции 1-400) | 24 KB | ~8 |
| 8 | [`docs/UX_PERFORMANCE_AUDIT.md`](docs/UX_PERFORMANCE_AUDIT.md) | ✅ Прочитан полностью | 7 KB | ~9 |
| 9 | [`docs/REFACTORING_TASKS.md`](docs/REFACTORING_TASKS.md) | ✅ Прочитан полностью | 16 KB | ~55 |
| 10 | [`docs/MIGRATION_PLAN.md`](docs/MIGRATION_PLAN.md) | ✅ Прочитан (секции 1-400) | 72 KB | ~15 |
| 11 | [`Promts/Claude Sonnet-4.6 fix.md`](Promts/Claude%20Sonnet-4.6%20fix.md) | ✅ Прочитан полностью | ~5 KB | ~24 |
| 12 | [`Promts/GLM-5.2 fix1.md`](Promts/GLM-5.2%20fix1.md) | ✅ Прочитан частично | ~10 KB | ~34 |
| 13 | [`Promts/GLM-5.2 fix2.md`](Promts/GLM-5.2%20fix2.md) | ✅ Прочитан полностью | ~6 KB | ~30 |
| 14 | [`Promts/GLM-5.2 fix3.md`](Promts/GLM-5.2%20fix3.md) | ✅ Прочитан частично | ~10 KB | ~26 |
| 15 | [`Promts/GLM-5.2 fix4.md`](Promts/GLM-5.2%20fix4.md) | ✅ Прочитан частично | ~20 KB | ~24 |
| 16 | [`Promts/GLM-5.2 fix5.md`](Promts/GLM-5.2%20fix5.md) | ✅ Прочитан частично | ~22 KB | ~24 |
| 17 | [`app/__init__.py`](app/__init__.py) | ✅ Прочитан полностью | 21 KB | ~5 |

### Файлы, не найденные в проекте

| Файл | Примечание |
|------|------------|
| `additional_audit_prompt.md` | Не существует в репозитории |
| `additional_audit_prompt_part3.md` | Не существует в репозитории |
| `additional_audit_prompt_part4.md` | Не существует в репозитории |
| `additional_audit_prompt_part5.md` | Не существует в репозитории |
| `ai_agent_test_prompt.md` | Не существует в репозитории |
| `comprehensive_test_plan.md` | Не существует в репозитории |
| `Trudnik_Flask_Architecture_Audit.docx` | Не существует в репозитории (формат DOCX) |
| `Trudnik_Refactoring_Pull_Requests.docx` | Не существует в репозитории (формат DOCX) |

---

## 2. Систематизированные рекомендации по тематикам

### 2.1 Архитектура

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| ARCH-01 | Расщепить `utils.py` (1592 строки, 66K) на 9 модулей: `supabase_client.py`, `auth_service.py`, `storage_service.py`, `geo_service.py`, `ratings_service.py`, `utils/postgrest.py`, `utils/formatting.py`, `utils/pagination.py`, `validators.py`, `context_processors.py` | CODE_REVIEW_FINAL_REPORT §2.4, REFACTORING_TASKS #23 | Не реализовано |
| ARCH-02 | Ввести паттерн Data Access Layer (Repository) для стандартизации PostgREST-запросов: `JobRepository`, `ApplicationRepository` | CODE_REVIEW_FINAL_REPORT §5.2 | Не реализовано |
| ARCH-03 | Создать `ApplicationService` — вынести бизнес-логику откликов из [`applications.py`](app/blueprints/applications.py) | REFACTORING_TASKS #24, GLM-5.2 fix3 #118 | Не реализовано |
| ARCH-04 | Унифицировать обработку ошибок PostgREST: `assert_postgrest_ok(resp, operation, context)` | CODE_REVIEW_FINAL_REPORT §5.4, REFACTORING_TASKS #42 | Не реализовано |
| ARCH-05 | Ввести Dependency Injection для сервисов через `app.extensions` вместо чтения `os.environ` | CODE_REVIEW_FINAL_REPORT §5.6, REFACTORING_TASKS #27 | Частично |
| ARCH-06 | Вынести accept/reject/reopen API-роуты из [`app/__init__.py`](app/__init__.py) обратно в [`applications.py`](app/blueprints/applications.py) | CODE_REVIEW_CONTEXT §5.1 | Не реализовано |
| ARCH-07 | Унифицировать два механизма отзыва заявки: оставить только `api_withdraw_application()`, удалить `unapply_job()` (DELETE) | REFACTORING_TASKS #25 | Не реализовано |
| ARCH-08 | Извлечь общую функцию `_apply_geo_filters()` — `search_jobs()` и `search_workers()` имеют ~80% совпадения | REFACTORING_TASKS #28 | Не реализовано |
| ARCH-09 | Убрать дублирование `list_invitations()` в [`jobs_api.py`](app/blueprints/jobs_api.py) и [`jobs.py`](app/blueprints/jobs.py) | REFACTORING_TASKS #29 | Не реализовано |
| ARCH-10 | Все защищённые эндпоинты — через `@role_required`, убрать ручные проверки `session.get("user_role")` | REFACTORING_TASKS #26 | Частично |
| ARCH-11 | Вынести все контекст-процессоры в [`context_processors.py`](app/context_processors.py) (частично сделано) | CODE_REVIEW_FINAL_REPORT §2.4 | Частично |
| ARCH-12 | Создать отдельный WebSocket-сервер с правильной архитектурой (сейчас дублирование токенов, несовместимость JWT-форматов) | GLM-5.2 fix1 #7, #30, GLM-5.2 fix2 #66, GLM-5.2 fix5 #262 | Не реализовано |
| ARCH-13 | Внедрить feature flags для платных/бесплатных функций | Все audit-файлы | Не реализовано |

### 2.2 Безопасность

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| SEC-01 | Утечка `password_hash`, `inn`, `phone`, `email` через `public_profile` — заменить `select=*` на `PUBLIC_PROFILE_FIELDS` | trudnik_fix_prompt §1.1 | Частично |
| SEC-02 | PostgREST-инъекция через `<app_id>` без `@validate_uuid` | trudnik_fix_prompt §1.2 | Частично |
| SEC-03 | `SECRET_KEY` используется как `X-Admin-Token` — ввести `ADMIN_API_TOKEN` | trudnik_fix_prompt §1.3, GLM-5.2 fix1 #3, Claude fix #5 | Частично |
| SEC-04 | RLS: `profiles` SELECT открывает все поля, INSERT позволяет создать admin | trudnik_fix_prompt §1.4 | Частично |
| SEC-05 | `register_user` RPC принимает `role='admin'` — добавить валидацию | trudnik_fix_prompt §1.5 | Частично |
| SEC-06 | `delete_job_cascade` и `delete_user_cascade` доступны `authenticated` — ограничить `service_role` | trudnik_fix_prompt §1.6 | Частично |
| SEC-07 | `apply_job_atomic` двойной инкремент `current_workers` — исправить логику | trudnik_fix_prompt §1.7 | Не реализовано |
| SEC-08 | `jobs.status` CHECK-конструкция не содержит все статусы — расширить | trudnik_fix_prompt §1.8 | Частично |
| SEC-09 | `accept_application`/`reject_application` без проверки владельца задания | trudnik_fix_prompt §1.9 | Не реализовано |
| SEC-10 | `messages` INSERT позволяет писать в любой `application_id` — исправить RLS | trudnik_fix_prompt §1.10 | Не реализовано |
| SEC-11 | `notifications` и `email_log` INSERT открыты для всех — ограничить `service_role` | trudnik_fix_prompt §1.11 | Не реализовано |
| SEC-12 | Bcrypt rounds = 6 (OWASP требует >=12) — повысить до 12 | trudnik_fix_prompt §1.12, GLM-5.2 fix1 #3 | Не реализовано |
| SEC-13 | `/login` и `/register` без CSRF — добавить CSRF-токены | trudnik_fix_prompt §1.13 | Не реализовано |
| SEC-14 | `login_required` проглатывает ошибки JWT decode — заменить `pass` на `session.clear()` | trudnik_fix_prompt §1.15 | Не реализовано |
| SEC-15 | `admin_required` не перечитывает role из БД — добавить DB-перепроверку | trudnik_fix_prompt §1.16 | Не реализовано |
| SEC-16 | Rate limit на `/login` слабый, fail-open — добавить per-account lockout, fail-closed | trudnik_fix_prompt §1.17 | Не реализовано |
| SEC-17 | JWT role захардкожен на `'trudnikapp'` (RLS bypassed) — использовать реальную роль из сессии | trudnik_fix_prompt §1.18 | Не реализовано |
| SEC-18 | Хардкод секретов в `.env`, `amvera.yml`, скриптах — удалить из репозитория, использовать env vars | CODE_REVIEW_FINAL_REPORT §2.7, Claude fix #1, GLM-5.2 fix1 #1 | Частично |
| SEC-19 | `PGRST_JWT_SECRET` в debug-логах — убрать из логов | Claude fix #2, GLM-5.2 fix1 #2 | Не реализовано |
| SEC-20 | Wildcard CORS для WebSocket — ограничить origins | Claude fix #3 | Не реализовано |
| SEC-21 | JWT-токен в URL query-параметре WebSocket — передавать в первом WS-сообщении | Claude fix #4 | Не реализовано |
| SEC-22 | CSRF bypass через path-whitelist (admin endpoints) | Claude fix #5 | Частично |
| SEC-23 | CSRF-токен сравнивается через `!=` вместо `hmac.compare_digest` | GLM-5.2 fix1 #5 | Не реализовано |
| SEC-24 | `login_user` RPC без `SET search_path = ''` — уязвимость к подмене функций | GLM-5.2 fix1 #6 | Не реализовано |
| SEC-25 | JWT claim mismatch: Flask использует `sub`, RLS проверяет `user_id` — RLS не работает | GLM-5.2 fix1 #7 | Не реализовано |
| SEC-26 | Stored XSS через `raterName` в [`job_detail.html`](templates/job_detail.html) | GLM-5.2 fix1 #8 | Не реализовано |
| SEC-27 | XSS через flash-сообщения в [`base.html`](templates/base.html) | GLM-5.2 fix1 #9 | Не реализовано |
| SEC-28 | XSS через атрибут `value="${s.name}"` в [`admin.html`](templates/admin.html) | GLM-5.2 fix1 #10 | Не реализовано |
| SEC-29 | No-op escape в [`_filter_skills.html`](templates/_filter_skills.html) — замена `"` на `"` | GLM-5.2 fix1 #11 | Не реализовано |
| SEC-30 | Timing-enumeration аккаунтов через password-reset | GLM-5.2 fix1 #12 | Не реализовано |
| SEC-31 | Lockout по email без rate-limit на IP — возможность DoS аккаунтов | GLM-5.2 fix1 #13 | Не реализовано |
| SEC-32 | Path traversal в `/uploads/<path:filename>` — использовать абсолютный путь | Claude fix #16 | Не реализовано |
| SEC-33 | Поля профиля без валидации длины — возможна перегрузка | Claude fix #17 | Не реализовано |
| SEC-34 | `worker_contacts` раскрывает `email_public` вместо `email` и `phone` | GLM-5.2 fix5 #257 | Не реализовано |
| SEC-35 | Service Worker кэширует приватные страницы без проверки аутентификации | GLM-5.2 fix2 #68 | Не реализовано |
| SEC-36 | Service Worker удаляет CSP из кэшированных ответов | GLM-5.2 fix2 #68 | Не реализовано |
| SEC-37 | CSRF-токен в cookie вместо meta-тега (push-notifications.js) | GLM-5.2 fix2 #71 | Не реализовано |
| SEC-38 | `/health/postgrest` раскрывает внутренний URL — ограничить доступ | Claude fix #24 | Не реализовано |
| SEC-39 | Email-адрес вставляется в URL PostgREST без `sanitize_postgrest` | Claude fix #12 | Не реализовано |
| SEC-40 | `apply_selected()` обходит RPC `apply_job_atomic` — нет проверок blacklist/слотов | CODE_REVIEW_FINAL_REPORT #4 | Не реализовано |
| SEC-41 | `delete_subscription()` без проверки `user_id` — можно удалить чужую подписку | CODE_REVIEW_FINAL_REPORT #13, REFACTORING_TASKS #13 | Не реализовано |
| SEC-42 | `mark_read()` без проверки `user_id` — можно пометить чужие уведомления | REFACTORING_TASKS #16 | Не реализовано |
| SEC-43 | WebSocket-сервер: неверный секрет и неверный claim для JWT-проверки | GLM-5.2 fix1 #30 | Не реализовано |
| SEC-44 | `/apply/<job_id>` принимает GET — CSRF уязвимость через `<img>` | GLM-5.2 fix3 #104 | Не реализовано |
| SEC-45 | Мутирующие эндпоинты принимают GET: `/cancel-job`, `/restore-job`, `/delete-job` | GLM-5.2 fix3 #111 | Не реализовано |
| SEC-46 | `bulk_delete_*` без валидации UUID в массиве ID | GLM-5.2 fix2 #79 | Не реализовано |
| SEC-47 | `webhook verification` всегда возвращает True при не настроенной YooKassa | GLM-5.2 fix1 #34 | Не реализовано |

### 2.3 Производительность

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| PERF-01 | Неатомарные операции (check-then-act) — 15 race condition мест | CODE_REVIEW_FINAL_REPORT §2.1 | Частично |
| PERF-02 | Сломанная пагинация — фильтрация после limit/offset в Python | CODE_REVIEW_FINAL_REPORT §2.2, REFACTORING_TASKS #6-8 | Не реализовано |
| PERF-03 | In-memory состояние в multi-process окружении: email-лимит, rate-limit, Redis-соединение | CODE_REVIEW_FINAL_REPORT §2.3, REFACTORING_TASKS #9-12 | Не реализовано |
| PERF-04 | N+1 запросов в контекстном процессоре `inject_application_count` | UX_PERFORMANCE_AUDIT §1.1, REFACTORING_TASKS #35 | Не реализовано |
| PERF-05 | `job_detail` — 5+ последовательных запросов к PostgREST | UX_PERFORMANCE_AUDIT §1.1, Claude fix #86, GLM-5.2 fix2 #86 | Не реализовано |
| PERF-06 | Декоратор `cache_for` существует, но не используется нигде | UX_PERFORMANCE_AUDIT §2.2 | Не реализовано |
| PERF-07 | Отсутствие HTTP-заголовков кэширования для статики | UX_PERFORMANCE_AUDIT §2.2 | Частично |
| PERF-08 | Отсутствие кэширования справочных данных (навыки/религии) | UX_PERFORMANCE_AUDIT §2.2 | Не реализовано |
| PERF-09 | Нет purging неиспользуемого CSS в Tailwind (33 KB) | UX_PERFORMANCE_AUDIT §2.1 | Не реализовано |
| PERF-10 | Отсутствие пагинации по умолчанию на главной | UX_PERFORMANCE_AUDIT §2.1 | Частично |
| PERF-11 | 8 последовательных HTTP-запросов в дашборде админки | Claude fix #10, GLM-5.2 fix1 #16 | Не реализовано |
| PERF-12 | `inject_application_count` кэшируется 30 сек, но не инвалидируется при новых откликах | GLM-5.2 fix2 #81 | Не реализовано |
| PERF-13 | `role_required` делает HTTP-запрос к PostgREST на каждый запрос (N+1) | Claude fix #9 | Не реализовано |
| PERF-14 | Загрузка до 500 заявок для фильтра по навыкам — фильтрация в Python | GLM-5.2 fix1 #14 | Не реализовано |
| PERF-15 | Блокирующий HTTP-запрос при старте приложения (`_wait_for_postgrest`) | GLM-5.2 fix1 #15, GLM-5.2 fix2 #80 | Не реализовано |
| PERF-16 | Загрузка ВСЕХ откликов пользователя без limit для пометки «откликнулся» | GLM-5.2 fix1 #17 | Не реализовано |
| PERF-17 | Обновление рейтинга отдельными запросами — заменить на RPC `recompute_user_rating` | GLM-5.2 fix1 #18 | Не реализовано |
| PERF-18 | Глобальные `requests.Session` без connection limit — исчерпание соединений | GLM-5.2 fix1 #19, Claude fix #14 | Не реализовано |
| PERF-19 | Кэш `cache_for` может течь память — добавить LRU eviction | Claude fix #23, GLM-5.2 fix1 #20 | Не реализовано |
| PERF-20 | `Cache-Control: no-store` для `/uploads/` — фото не кэшируются | GLM-5.2 fix1 #27 | Не реализовано |
| PERF-21 | `_get_smtp_connection` без таймаута на `starttls()` и `login()` | GLM-5.2 fix2 #75 | Не реализовано |
| PERF-22 | `get_unread_count()` с `limit=100` — недоучёт при >100 | REFACTORING_TASKS #15 | Не реализовано |
| PERF-23 | `my_applications()` без пагинации — загрузка всех заявок | REFACTORING_TASKS #32 | Не реализовано |
| PERF-24 | Подсчёт статистики дашборда — count без `Prefer: count=exact` | REFACTORING_TASKS #33 | Не реализовано |
| PERF-25 | `enrich_job_with_references` делает 2 дополнительных запроса на каждый job (N+1) | GLM-5.2 fix2 #85 | Не реализовано |
| PERF-26 | `_login_direct_sql` открывает новое соединение на каждый логин | GLM-5.2 fix1 #31 | Не реализовано |
| PERF-27 | `get_job_ratings` делает 2 запроса вместо 1 для одной таблицы | GLM-5.2 fix3 #121 | Не реализовано |
| PERF-28 | `send_batch()` синхронный цикл вместо Celery group | REFACTORING_TASKS #30 | Не реализовано |
| PERF-29 | Загрузка всех push-подписок в память без пагинации | REFACTORING_TASKS #31 | Не реализовано |
| PERF-30 | Дублирующие запросы в `my_jobs()` | REFACTORING_TASKS #34 | Не реализовано |
| PERF-31 | `postgrest_request` повторяет запрос при 401 с `time.sleep(0.5)` — блокировка worker'а | GLM-5.2 fix2 #88 | Не реализовано |
| PERF-32 | `_check_postgrest_health` выполняется внутри Lock — блокировка всех потоков | GLM-5.2 fix2 #90 | Не реализовано |
| PERF-33 | `delete_user_cascade` делает цикл 1000+ вызовов `delete_job_cascade` | GLM-5.2 fix5 #255 | Не реализовано |
| PERF-34 | `my_jobs_action` делает отдельный GET для проверки ownership каждого задания — N+1 | GLM-5.2 fix3 #117 | Не реализовано |

### 2.4 Пользовательский опыт (UX)

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| UX-01 | Отсутствует пагинация на главной странице — пользователь видит только первые 20 заданий | GLM-5.2 fix4 #151 | Не реализовано |
| UX-02 | Вкладка «Статистика» в админке показывает «Статистика загружена» без реальных цифр | GLM-5.2 fix4 #152, #159 | Не реализовано |
| UX-03 | Кнопка «Добавить навык/вероисповедание» в админке не работает (JSON vs form-data mismatch) | GLM-5.2 fix4 #155 | Не реализовано |
| UX-04 | Login не обрабатывает `?next=` параметр — пользователь теряет контекст | GLM-5.2 fix3 #105 | Не реализовано |
| UX-05 | После отклика трудник редиректится на главную, а не обратно к заданию | GLM-5.2 fix3 #106 | Не реализовано |
| UX-06 | Кнопка «Написать в чат» не работает для трудников (`@role_required('employer')` на `/chat/new/<worker_id>`) | GLM-5.2 fix3 #101 | Не реализовано |
| UX-07 | `chat_title` и `chat_subtitle` не передаются в шаблон — всегда «Чат» | GLM-5.2 fix3 #109 | Не реализовано |
| UX-08 | Чат доступен только при `job.status == 'completed'` в UI, но сервер разрешает при accepted | GLM-5.2 fix3 #119 | Не реализовано |
| UX-09 | «Удаление чата» удаляет только сообщения, но чат восстанавливается пустым | GLM-5.2 fix3 #120 | Не реализовано |
| UX-10 | Отсутствуют шаблоны `password_reset_request.html` и `password_reset_confirm.html` | GLM-5.2 fix3 #96 | Не реализовано |
| UX-11 | Навыки трудника НЕ сохраняются при регистрации (формат данных mismatch) | GLM-5.2 fix3 #97 | Не реализовано |
| UX-12 | Навыки НЕ сохраняются при редактировании профиля (JSON.stringify vs comma-separated) | GLM-5.2 fix3 #98 | Не реализовано |
| UX-13 | Квота заданий НЕ декрементируется при создании — монетизация неработоспособна | GLM-5.2 fix3 #99 | Не реализовано |
| UX-14 | `audit_log` записывает `user_id = None` (session.get('user', {}).get('id') не существует) | GLM-5.2 fix3 #100 | Не реализовано |
| UX-15 | Сломанная иконка в пустом состоянии `/workers` (users vs users_icon) | GLM-5.2 fix3 #102 | Не реализовано |
| UX-16 | Импорт несуществующих иконок в `my_applications.html` | GLM-5.2 fix3 #103 | Не реализовано |
| UX-17 | У трудника нет страницы «Мои отклики» — критический UX-провал | GLM-5.2 fix4 #170 | Не реализовано |
| UX-18 | `my_applications` игнорирует `?job_id=` параметр | GLM-5.2 fix3 #115 | Не реализовано |
| UX-19 | Главная страница никогда не подсвечивается как активная в навигации | GLM-5.2 fix4 #166 | Не реализовано |
| UX-20 | Проверка `'substring' in request.endpoint` вместо точного сравнения (false positives) | GLM-5.2 fix4 #167 | Не реализовано |
| UX-21 | Нижняя навигация для трудника: кнопка «Отклики» ведёт на `/my-applications` (только для employer) | GLM-5.2 fix4 #169 | Не реализовано |
| UX-22 | `delete_job` без cleanup orphaned-файлов (`job_photos`, verification docs) | GLM-5.2 fix4 #162, #163 | Не реализовано |
| UX-23 | `window.TRUDNIK_CONFIG` без `userId` — все сообщения чата отображаются как «не мои» | GLM-5.2 fix5 #261 | Не реализовано |
| UX-24 | `delete-all` уведомлений с пробелом в URL-фильтре — не удаляет приглашения | GLM-5.2 fix3 #107 | Не реализовано |
| UX-25 | `username` колонка не существует в БД — email-уведомления: «Здравствуйте, Пользователь!» | GLM-5.2 fix3 #108 | Не реализовано |
| UX-26 | `addSkill`/`addReligion` игнорируют ошибки — кнопка молча не работает | GLM-5.2 fix4 #156 | Не реализовано |
| UX-27 | `bulk_delete` без защиты от двойного клика и повторной отправки | GLM-5.2 fix4 #161 | Не реализовано |
| UX-28 | Ссылка на несуществующий endpoint `profile.profile_edit` | GLM-5.2 fix4 #165 | Не реализовано |
| UX-29 | Создание задания без `is_paid` — задание невидимо в поиске при монетизации | GLM-5.2 fix4 #172 | Не реализовано |
| UX-30 | `approve_employer` не проверяет роль — можно «верифицировать» трудника | GLM-5.2 fix4 #160 | Не реализовано |
| UX-31 | Service Worker ломает logout и кэширует приватные данные | GLM-5.2 fix3 #110 | Не реализовано |
| UX-32 | `tariff` рассинхронизация: БД='standard', subscriptions='basic', UI='Базовый' | GLM-5.2 fix5 #258 | Не реализовано |
| UX-33 | Регистрация работодателя без создания `employer_subscriptions` | GLM-5.2 fix5 #259 | Не реализовано |

### 2.5 Монетизация

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| MON-01 | Создать полноценный `PaymentService` с поддержкой YooKassa/Stripe | CODE_REVIEW_FINAL_REPORT, MIGRATION_PLAN, BUSINESS_LOGIC | Частично (заглушка) |
| MON-02 | Реализовать модель подписок (basic/pro/business) с квотами на задания | CODE_REVIEW_FINAL_REPORT, BUSINESS_LOGIC | Не реализовано |
| MON-03 | Внедрить `is_paid` логику — сейчас `is_paid=True` всегда, но без реальной оплаты | BUSINESS_LOGIC §2.6 | Не реализовано |
| MON-04 | Унифицировать `tariff_key` во всех таблицах (`standard`/`basic`/`pro`/`business`) | GLM-5.2 fix5 #258 | Не реализовано |
| MON-05 | Создать запись в `employer_subscriptions` при регистрации работодателя | GLM-5.2 fix5 #259 | Не реализовано |
| MON-06 | Декрементировать `jobs_remaining` при создании задания | GLM-5.2 fix3 #99 | Не реализовано |
| MON-07 | Вебхук YooKassa: проверка подписи обязательна, не возвращать True при не настроенной | GLM-5.2 fix1 #34 | Не реализовано |
| MON-08 | Исправить `hmac.new` в `payment_service.py` (хотя работает) | Claude fix #18 | Не реализовано |
| MON-09 | Реализовать страницу `/pricing` с тарифами и подключением | Все audit-файлы | Не реализовано |
| MON-10 | Создать страницу истории платежей для пользователя | Все audit-файлы | Не реализовано |
| MON-11 | Внедрить feature flags для платных/бесплатных функций | Все audit-файлы | Не реализовано |
| MON-12 | Гарантировать, что базовые функции (поиск, регистрация, отклики) всегда бесплатны | Все audit-файлы | Не реализовано |
| MON-13 | Раскрытие контактов за плату — функционал неактивен | BUSINESS_LOGIC §2.6 | Не реализовано |
| MON-14 | Чеки самозанятого (`receipts`) — таблица существует, не используется | BUSINESS_LOGIC | Не реализовано |

### 2.6 Тестирование

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| TST-01 | Создать комплексный тестовый план по 7 слоям (TESTS_NEW_ARCH.md) | TESTS_NEW_ARCH | Не реализовано |
| TST-02 | Unit-тесты для всех RPC-функций: `register_user`, `login_user`, `apply_job_atomic`, etc. | TESTS_NEW_ARCH §1.1-1.3 | Частично |
| TST-03 | Интеграционные тесты JWT: подделка, истечение, algorithm confusion | TESTS_NEW_ARCH §1.2 | Не реализовано |
| TST-04 | Race condition тесты: 50 concurrent applies → только 3 accepted | TESTS_NEW_ARCH #3 | Не реализовано |
| TST-05 | Тесты Path Traversal + SQL Injection | TESTS_NEW_ARCH #4 | Не реализовано |
| TST-06 | Тесты Circuit Breaker: 5 ошибок → OPEN → HALF_OPEN → CLOSED | TESTS_NEW_ARCH #5 | Не реализовано |
| TST-07 | E2E тесты для полного цикла трудника и работодателя | TESTS_NEW_ARCH §5 | Не реализовано |
| TST-08 | Playwright тесты для 270+ кнопок из BUTTON_REGISTRY.md | TESTS_NEW_ARCH §3.1 | Не реализовано |
| TST-09 | Тесты accessibility (WCAG 2.1 AA): aria-label, focus trapping, color contrast | TESTS_NEW_ARCH §3.3 | Не реализовано |
| TST-10 | Тесты Service Worker: кэширование, offline, push-подписки | TESTS_NEW_ARCH §4 | Не реализовано |
| TST-11 | Обновить `conftest.py` для поддержки in-memory Mock PostgREST | TESTS_NEW_ARCH | Частично |
| TST-12 | Тесты для всех 14 типов уведомлений | TESTS_NEW_ARCH | Не реализовано |
| TST-13 | Тесты email-отправки: лимиты, шаблоны, retry | TESTS_NEW_ARCH | Не реализовано |
| TST-14 | Тесты WebSocket: JWT-аутентификация, Pub/Sub, fallback polling | TESTS_NEW_ARCH §4.2 | Не реализовано |
| TST-15 | Тесты загрузки файлов: MIME-валидация, размер, `/uploads/` traversal | TESTS_NEW_ARCH §1.4 | Не реализовано |

### 2.7 Документация

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| DOC-01 | Обновить `PROJECT_CONTEXT.md`: количество blueprint'ов (13, не 10), версия Python (3.12, не 3.14), удалить `shifts.py` | CODE_REVIEW_FINAL_REPORT §2.6, REFACTORING_TASKS #39 | Не реализовано |
| DOC-02 | Обновить `API_REFERENCE.md`: удалить ссылки на несуществующие JS-файлы | REFACTORING_TASKS #40 | Не реализовано |
| DOC-03 | Обновить `SECURITY.md`: убрать упоминания Supabase Realtime, email verification (не реализован) | CODE_REVIEW_FINAL_REPORT §2.6 | Не реализовано |
| DOC-04 | Обновить `ARCHITECTURE.md`: убрать упоминания несуществующих `static/js/` файлов | CODE_REVIEW_FINAL_REPORT §2.6 | Не реализовано |
| DOC-05 | Документировать все RPC-функции с сигнатурами и бизнес-правилами | CODE_REVIEW_FINAL_REPORT | Не реализовано |
| DOC-06 | Создать `docs/MONETIZATION.md` с описанием модели монетизации | Все audit-файлы | Не реализовано |
| DOC-07 | Обновить `README.md` с актуальной архитектурой (Amvera вместо Supabase) | Все audit-файлы | Частично |
| DOC-08 | Добавить архитектурные схемы в формате Mermaid для потоков данных | ARCHITECTURE.md | Частично |

### 2.8 Инфраструктура и DevOps

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| INF-01 | Исправить Dockerfile: `FROM python:3.12-slim` (было 3.11) | CODE_REVIEW_FINAL_REPORT #3 | Не реализовано |
| INF-02 | Раскомментировать `USER appuser` в Dockerfile (non-root) | CODE_REVIEW_FINAL_REPORT #5 | Не реализовано |
| INF-03 | Добавить `HEALTHCHECK` в Dockerfile | REFACTORING_TASKS #46 | Не реализовано |
| INF-04 | Унифицировать `FLASK_ENV` → `DEPLOYMENT_ENV` | REFACTORING_TASKS #44 | Не реализовано |
| INF-05 | Удалить неиспользуемые зависимости: `openai`, `Flask-Login`, `gunicorn`, `fpdf2` | REFACTORING_TASKS #45 | Не реализовано |
| INF-06 | Перенести in-memory rate limit в Redis для multi-worker | CODE_REVIEW_FINAL_REPORT §2.3, REFACTORING_TASKS #11 | Не реализовано |
| INF-07 | Перенести дневной лимит email в Redis (вместо in-memory `_daily_count`) | REFACTORING_TASKS #9 | Не реализовано |
| INF-08 | Исправить восстановление Redis-соединения в `redis_publisher.py` | REFACTORING_TASKS #10 | Не реализовано |
| INF-09 | Добавить `--down` секции в миграции (rollback) | REFACTORING_TASKS #51 | Не реализовано |
| INF-10 | Проверить и обновить CI/CD (GitHub Actions) для Amvera | REFACTORING_TASKS #55 | Не реализовано |
| INF-11 | Исправить `db_pool.py`: неверные env vars, thread-unsafe pool | GLM-5.2 fix1 #22 | Не реализовано |
| INF-12 | `_wait_for_postgrest` блокирует старт — перенести в `before_first_request` или убрать | GLM-5.2 fix1 #15, GLM-5.2 fix5 #263 | Не реализовано |
| INF-13 | Добавить `worker_startup_delay` для Celery (ждёт PostgREST) | GLM-5.2 fix5 #263 | Не реализовано |
| INF-14 | Переименовать дубликат номера миграции 019 в 019b | REFACTORING_TASKS #47 | Не реализовано |
| INF-15 | Унифицировать `VERSION` на SemVer | REFACTORING_TASKS #48 | Не реализовано |
| INF-16 | Настроить мониторинг (Prometheus/Grafana) для PostgREST, Redis, Celery | CODE_REVIEW_FINAL_REPORT | Не реализовано |
| INF-17 | Настроить алертинг для платёжных операций | MIGRATION_PLAN, BUSINESS_LOGIC | Не реализовано |
| INF-18 | SMTP connection pooling не потокобезопасно — убрать pooling для Celery | GLM-5.2 fix1 #32 | Не реализовано |
| INF-19 | Celery worker не ждёт PostgREST при старте — задачи теряются | GLM-5.2 fix5 #263 | Не реализовано |
| INF-20 | `requests.Session` не thread-safe для gunicorn workers — использовать `threading.local()` | Claude fix #14 | Не реализовано |

### 2.9 Кодовая база и рефакторинг

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| REF-01 | Убрать локальные импорты внутри функций (8+ мест) | CODE_REVIEW_FINAL_REPORT §2.5, REFACTORING_TASKS #49 | Не реализовано |
| REF-02 | Унифицировать HTTP-клиенты в скриптах: заменить `requests` на `httpx` | REFACTORING_TASKS #50 | Не реализовано |
| REF-03 | Исправить несуществующие колонки в cleanup/preseed скриптах | REFACTORING_TASKS #52 | Не реализовано |
| REF-04 | Убрать авто-отметку уведомлений прочитанными — отмечать только при явном действии | REFACTORING_TASKS #53 | Не реализовано |
| REF-05 | Добавить `favorite_type` в `check_favorite_api` | REFACTORING_TASKS #54 | Не реализовано |
| REF-06 | Исправить `NameError` в `auth.py` — `err_data` не инициализирован до `try` | REFACTORING_TASKS #19 | Не реализовано |
| REF-07 | Исправить проверку чата: разрешить для accepted-заявок, не только completed | REFACTORING_TASKS #43 | Не реализовано |
| REF-08 | Заменить `send_batch()` синхронный цикл на Celery group | REFACTORING_TASKS #30 | Не реализовано |
| REF-09 | Добавить колонку `job_id` в таблицу `notifications` | REFACTORING_TASKS #38 | Не реализовано |
| REF-10 | Вынести очистку orphaned-уведомлений в Celery-задачу | REFACTORING_TASKS #37 | Не реализовано |
| REF-11 | KeyError при отсутствии ключей в JSON (`chat.py`) — использовать `.get()` | Claude fix #6 | Не реализовано |
| REF-12 | `ValueError` при невалидном вводе без обработки (`jobs.py`) | Claude fix #7 | Не реализовано |
| REF-13 | `applications(count)` embedded resource работает нестабильно | Claude fix #11 | Не реализовано |
| REF-14 | `sanitize_postgrest(now)` ломает ISO-формат timestamp (удаляет `:`) | Claude fix #15 | Не реализовано |
| REF-15 | Декораторы в неправильном порядке: `rate_limit` → `role_required` → `login_required` | Claude fix #19 | Не реализовано |
| REF-16 | `apply_job` без `@role_required('worker')` — работодатель может откликнуться | Claude fix #20 | Не реализовано |
| REF-17 | `application_id` не валидируется как UUID в `send_message()` | Claude fix #21 | Не реализовано |
| REF-18 | `cancel_application` проверяет 12-часовое окно, но не учитывает timezone | GLM-5.2 fix2 #84 | Не реализовано |
| REF-19 | `threading.Thread` для уведомлений без обработки ошибок | GLM-5.2 fix1 #21 | Не реализовано |
| REF-20 | `api_batch_applications` вызывает view-функцию как обычную — антипаттерн | GLM-5.2 fix2 #92, GLM-5.2 fix3 #118 | Не реализовано |
| REF-21 | `my_jobs_action` без валидации action и job_ids | GLM-5.2 fix2 #94 | Не реализовано |
| REF-22 | `reorder_skills`/`reorder_religions` без валидации UUID и ownership | GLM-5.2 fix4 #157 | Не реализовано |
| REF-23 | `moveSkill` не обрабатывает HTTP-ошибки reorder | GLM-5.2 fix4 #158 | Не реализовано |
| REF-24 | `delete_job` для админа без audit-log | GLM-5.2 fix3 #114 | Не реализовано |
| REF-25 | `_login_direct_sql` без логирования неудачных попыток | GLM-5.2 fix2 #89 | Не реализовано |
| REF-26 | `admin_panel` читает `actual_version` через `subprocess` на каждый запрос | GLM-5.2 fix2 #95 | Не реализовано |
| REF-27 | `circuit_breaker` считает 404 и 400 как ошибки — открывается при корректных запросах | GLM-5.2 fix1 #26 | Не реализовано |
| REF-28 | `delete_user_cascade` не удаляет `messages` где пользователь — получатель | GLM-5.2 fix5 #256 | Не реализовано |
| REF-29 | `delete_job_cascade` удаляет notifications по `message ILIKE` — риск удаления нерелевантных | GLM-5.2 fix5 #254 | Не реализовано |
| REF-30 | `create()` в notification_service не включает `title` в payload — нарушает NOT NULL | GLM-5.2 fix5 #251 | Не реализовано |
| REF-31 | `notification_outbox` без Celery-задачи для обработки — уведомления не доставляются | GLM-5.2 fix5 #252 | Не реализовано |
| REF-32 | `notification_id: int` в email_tasks, но в БД это UUID | GLM-5.2 fix5 #253 | Не реализовано |
| REF-33 | `_check_daily_limit` с race condition — expire только при current==1 | GLM-5.2 fix5 #274 | Не реализовано |
| REF-34 | `_time_module.timedelta` AttributeError — `time` модуль не имеет `timedelta` | GLM-5.2 fix1 #33, GLM-5.2 fix5 #273 | Не реализовано |
| REF-35 | Debug-логирование каждого WebSocket-подключения с уровнем WARNING | GLM-5.2 fix1 #29 | Не реализовано |
| REF-36 | `profile_resp` запрашивает `email,username` — `username` не существует | GLM-5.2 fix2 #93 | Не реализовано |
| REF-37 | `respond_invitation` не проверяет ownership для accept | GLM-5.2 fix3 #113 | Не реализовано |
| REF-38 | `request.get_json()` без `silent=True` в множестве мест | GLM-5.2 fix2 #73 | Не реализовано |

### 2.10 База данных и миграции

| ID | Рекомендация | Источник | Состояние |
|----|-------------|----------|-----------|
| DB-01 | Добавить column-level GRANT для `profiles` — исключить `password_hash`, `inn`, `phone`, `email` | trudnik_fix_prompt §1.1, §1.4 | Частично |
| DB-02 | Создать недостающие RPC: `withdraw_application_atomic`, `cancel_worker_atomic`, `cancel_job_atomic`, `force_complete_job`, `accept_invitation_atomic`, `register_user_full`, `delete_skill_cascade`, `upsert_rating_atomic`, `toggle_favorite_atomic`, `search_jobs_page` | CODE_REVIEW_FINAL_REPORT §2.1, REFACTORING_TASKS #1-5 | Частично |
| DB-03 | Исправить `apply_job_atomic` — убрать двойной инкремент `current_workers` | trudnik_fix_prompt §1.7 | Не реализовано |
| DB-04 | Расширить `jobs.status` CHECK-конструкцию: добавить `'active'`, `'in_progress'`, `'draft'`, `'paid'`, `'expired'` | trudnik_fix_prompt §1.8 | Частично |
| DB-05 | Исправить RLS: `accept_application`/`reject_application` без проверки владельца | trudnik_fix_prompt §1.9 | Не реализовано |
| DB-06 | Исправить RLS: `messages` INSERT — только участники application | trudnik_fix_prompt §1.10 | Не реализовано |
| DB-07 | Исправить RLS: `notifications` и `email_log` INSERT — только service_role | trudnik_fix_prompt §1.11 | Не реализовано |
| DB-08 | Повысить bcrypt rounds до 12 в `register_user`, `change_password`, `login_user` | trudnik_fix_prompt §1.12 | Не реализовано |
| DB-09 | Добавить rehash-on-login: обновлять хэш пароля при rounds=6 | trudnik_fix_prompt §1.12 | Не реализовано |
| DB-10 | Унифицировать сигнатуру `register_user` между 067 и `manual_fix_all.sql` | trudnik_fix_prompt §1.5 | Частично |
| DB-11 | Добавить `SET search_path = ''` в `login_user` RPC | GLM-5.2 fix1 #6 | Не реализовано |
| DB-12 | Исправить RLS-политики: использовать `request.jwt.claim.user_id` (добавить claim в JWT) | GLM-5.2 fix1 #7 | Не реализовано |
| DB-13 | `notifications.title TEXT NOT NULL` — но код не передаёт `title` в payload | GLM-5.2 fix5 #251 | Не реализовано |
| DB-14 | Унифицировать `tariff` во всех таблицах: заменить `'standard'` → `'basic'` | GLM-5.2 fix5 #258 | Не реализовано |
| DB-15 | Создать индексы для FTS, гео-поиска, частых запросов (GIN, GiST, B-tree) | MIGRATION_PLAN, UX_PERFORMANCE_AUDIT | Частично |
| DB-16 | Добавить `ON DELETE SET NULL` FK для `notifications.job_id` вместо ILIKE-удаления | GLM-5.2 fix5 #254 | Не реализовано |
| DB-17 | Создать Celery-задачу `process_notification_outbox` для обработки pending-уведомлений | GLM-5.2 fix5 #252 | Не реализовано |
| DB-18 | Добавить таблицу `feature_flags` для управления платными/бесплатными функциями | Все audit-файлы | Не реализовано |

---

## 3. Приоритизация: Внедрить / Отложить / Отклонить

### Категория A — ВНЕДРИТЬ СЕЙЧАС (P0-P1): 35 рекомендаций

Критические для стабильности и безопасности, блокируют развитие, быстро реализуемы или имеют высокий ROI.

| # | ID | Суть | Причина |
|---|-----|------|---------|
| 1 | SEC-01 | Утечка `password_hash`, `inn`, `phone`, `email` через `public_profile` | Критическая утечка ПДн |
| 2 | SEC-02 | PostgREST-инъекция через `<app_id>` без `@validate_uuid` | Инъекция в БД |
| 3 | SEC-03 | `SECRET_KEY` как `X-Admin-Token` — ввести `ADMIN_API_TOKEN` | Компрометация всей системы |
| 4 | SEC-05 | `register_user` принимает `role='admin'` | Эскалация привилегий |
| 5 | SEC-06 | `delete_job_cascade`/`delete_user_cascade` доступны authenticated | Потеря данных |
| 6 | SEC-07 | `apply_job_atomic` двойной инкремент `current_workers` | Блокирует приём откликов |
| 7 | SEC-09 | `accept_application` без проверки владельца | Неавторизованный приём откликов |
| 8 | SEC-10 | `messages` INSERT позволяет писать в любой `application_id` | Доступ к чужим чатам |
| 9 | SEC-12 | Bcrypt rounds = 6 (OWASP >=12) | Быстрый брутфорс паролей |
| 10 | SEC-14 | `login_required` проглатывает ошибки JWT decode | Обход аутентификации |
| 11 | SEC-17 | JWT role = 'trudnikapp' (RLS bypassed) | RLS не работает |
| 12 | SEC-18 | Хардкод секретов в репозитории | Полная компрометация |
| 13 | SEC-23 | CSRF-токен через `!=` вместо `hmac.compare_digest` | Timing-атака |
| 14 | SEC-24 | `login_user` RPC без `SET search_path = ''` | Подмена функций |
| 15 | SEC-25 | JWT claim mismatch: `sub` vs `user_id` | RLS полностью не работает |
| 16 | SEC-44 | `/apply/<job_id>` принимает GET | CSRF-уязвимость |
| 17 | SEC-45 | Мутирующие эндпоинты принимают GET | CSRF-уязвимость |
| 18 | DB-01 | Column-level GRANT для `profiles` | Утечка ПДн |
| 19 | DB-03 | Исправить `apply_job_atomic` двойной инкремент | Блокировка приёма |
| 20 | DB-04 | Расширить `jobs.status` CHECK-конструкцию | Ошибки RPC |
| 21 | DB-11 | `SET search_path = ''` в `login_user` | Безопасность |
| 22 | REF-34 | `_time_module.timedelta` AttributeError | Все email-отправки падают |
| 23 | REF-31 | `notification_outbox` без Celery-задачи | Уведомления не доставляются |
| 24 | REF-30 | `create()` в notification_service без `title` — NOT NULL violation | Уведомления не сохраняются |
| 25 | PERF-13 | `role_required` делает HTTP-запрос на каждый запрос | N+1, замедление |
| 26 | PERF-15 | `_wait_for_postgrest` блокирует старт | 30-секундная задержка |
| 27 | PERF-20 | `Cache-Control: no-store` для `/uploads/` | Фото не кэшируются |
| 28 | PERF-22 | `get_unread_count()` с `limit=100` | Неверный счётчик |
| 29 | INF-01 | Dockerfile: `FROM python:3.12-slim` | Код несовместим с образом |
| 30 | INF-02 | Non-root пользователь в Docker | Безопасность контейнера |
| 31 | INF-06 | In-memory rate limit → Redis | Не работает в multi-worker |
| 32 | INF-07 | Дневной лимит email → Redis | Не соблюдается лимит |
| 33 | INF-08 | Redis-соединение не восстанавливается | Потеря уведомлений |
| 34 | INF-12 | `_wait_for_postgrest` → убрать из импорта | Блокировка старта |
| 35 | DB-12 | Исправить JWT claim для RLS | RLS не работает |

### Категория B — ОТЛОЖИТЬ (P2-P3): 180+ рекомендаций

Важные, но не критические; требуют значительных усилий; зависят от других задач; актуальны после внедрения монетизации.

*Все рекомендации, не вошедшие в категории A и C, автоматически попадают в категорию B. Они будут включены в Фазы 2 и 3 плана реализации.*

### Категория C — ОТКЛОНИТЬ: 12 рекомендаций

| # | ID | Рекомендация | Обоснование отклонения |
|---|-----|-------------|----------------------|
| 1 | ARCH-02 | Ввести паттерн Repository (Data Access Layer) для PostgREST-запросов | Избыточно для текущего масштаба проекта (13 blueprint'ов, монолит). Введение слоя Repository добавит значительную сложность без немедленной выгоды. Текущая функция `postgrest_request()` уже централизует HTTP-запросы. Repository-паттерн имеет смысл при переходе на микросервисную архитектуру или при 10x росте кодовой базы. Рекомендуется пересмотреть через 6-12 месяцев. |
| 2 | ARCH-05 | Dependency Injection через `app.extensions` для всех сервисов | Текущая архитектура использует синглтоны и модульные переменные, что адекватно для монолитного Flask-приложения с 5 сервисами. Внедрение DI-контейнера (например, `inject` или ручное управление через `app.extensions`) добавит сложность конфигурации и не решит ни одной критической проблемы. Существующий подход с `current_app.config` достаточен. DI может быть внедрён при миграции на FastAPI или асинхронную архитектуру. |
| 3 | REF-02 | Унифицировать HTTP-клиенты в скриптах: `requests` → `httpx` | Скрипты в `scripts/` (5 файлов) используются только для административных задач (миграции, создание таблиц) и не находятся на критическом пути выполнения. Замена `requests` на `httpx` в этих скриптах не даст измеримого прироста производительности, так как они выполняются редко и офлайн. Риски: `httpx` имеет другой API для синхронного использования, что может привести к регрессиям в миграционных скриптах. Текущий `requests` стабилен и отлажен. |
| 4 | DB-02 (часть) | Создать RPC `search_jobs_page` для пагинированного поиска | PostgREST уже поддерживает пагинацию через `limit` и `offset` на уровне HTTP-заголовков. Создание отдельной RPC для пагинации дублирует встроенную функциональность PostgREST и усложняет поддержку (нужно синхронизировать фильтры между SQL и HTTP). Вместо этого следует исправить фильтрацию на стороне Python (перенести в SQL-запросы через PostgREST), что решит проблему без создания новой RPC. |
| 5 | TST-08 | Playwright тесты для всех 270+ кнопок из BUTTON_REGISTRY.md | Полное покрытие всех 270 кнопок Playwright-тестами — чрезмерно трудоёмкая задача (оценка: 200+ человеко-часов) с низким ROI на текущем этапе. Многие кнопки являются вариациями одного и того же компонента. Вместо этого следует: (1) покрыть критические пользовательские пути (P0) — ~30 кнопок, (2) использовать snapshot-тестирование для UI-компонентов, (3) полное покрытие отложить до стабилизации UI после редизайна. |
| 6 | REF-01 | Убрать локальные импорты внутри функций (8+ мест) | Локальные импорты использованы осознанно для избежания циклических зависимостей и ленивой загрузки модулей (например, `from flask import current_app` внутри функции). В Flask-приложениях это распространённый паттерн. Вынос всех импортов на уровень модуля может создать циклические импорты между `app/__init__.py`, blueprints и services. Требует тщательного рефакторинга структуры импортов, что неоправданно на текущем этапе. |
| 7 | INF-09 | Добавить `--down` секции во все 58 миграций | Трудоёмкость (60+ человеко-часов) не оправдана, так как: (1) миграции уже применены на production, (2) откат миграций PostgreSQL — сложная операция с риском потери данных, (3) для новых миграций (начиная с 075) можно ввести обязательные `--down` секции. Старые миграции достаточно документировать, но не переписывать. |
| 8 | INF-14 | Переименовать дубликат номера миграции 019 → 019b | Косметическое изменение, не влияющее на функциональность. Миграция 019 уже применена на production. Переименование файла миграции может сломать систему версионирования `schema_migrations`, если она проверяет имена файлов. Риск нарушения production-окружения перевешивает выгоду от чистоты нумерации. |
| 9 | REF-08 | Заменить `send_batch()` синхронный цикл на Celery group | `send_batch()` используется редко (массовые рассылки администратором). Синхронный цикл даёт контролируемую нагрузку на SMTP-сервер (с паузой `SMTP_RATE_LIMIT_PAUSE`). Celery group отправит все задачи одновременно — риск превышения лимитов SMTP-провайдера и блокировки. Текущий подход безопаснее, хотя и медленнее. |
| 10 | TST-09 | Тесты accessibility (WCAG 2.1 AA) в полном объёме | Полное соответствие WCAG 2.1 AA требует значительных изменений в вёрстке (aria-label на всех элементах, focus trapping, color contrast). Для B2B-платформы с ограниченной аудиторией (религиозные организации) это избыточно на текущем этапе. Рекомендуется внедрять accessibility постепенно, начиная с критических элементов (формы, модальные окна), по мере роста пользовательской базы. |
| 11 | REF-05 | Добавить `favorite_type` в `check_favorite_api` | Текущая реализация избранного корректно различает типы (worker/employer) через разные таблицы и эндпоинты. Добавление `favorite_type` как явного фильтра — дублирование существующей логики. Фильтр уже применяется на уровне приложения через разные запросы к разным таблицам. Не требует исправления. |
| 12 | UX-16 | Импорт несуществующих иконок в `my_applications.html` | Неиспользуемые импорты в Jinja2 (`chat_bubble`, `send`, `phone` и др.) не вызывают ошибок — Jinja2 игнорирует undefined импорты. Это косметический дефект, который не влияет на рендеринг страницы. Может быть исправлен при ближайшем рефакторинге шаблонов, но не требует отдельной задачи. |

---

## 4. Трёхфазный план реализации

### Фаза 1: Быстрые победы (1-3 недели) — 35 задач

Критические исправления безопасности, стабильности и мелкие UX-улучшения.

| ID задачи | Название | Часы | Специалист | Зависимости | Файлы |
|-----------|----------|------|------------|-------------|-------|
| F1-SEC-01 | Исправить утечку ПДн через `public_profile` — заменить `select=*` на `PUBLIC_PROFILE_FIELDS` | 3 | Backend Python | Нет | `profile.py`, `auth.py`, `employers.py` |
| F1-SEC-02 | Добавить `@validate_uuid` на все маршруты с UUID-параметрами | 4 | Backend Python | Нет | `applications.py`, `jobs.py`, `admin.py`, `profile.py`, `ratings.py`, `chat.py`, `notifications.py` |
| F1-SEC-03 | Ввести `ADMIN_API_TOKEN`, отделить от `SECRET_KEY`, отключить деструктивные API в production | 3 | Backend Python | Нет | `config.py`, `__init__.py`, `admin.py` |
| F1-SEC-05 | Исправить `register_user` RPC — запретить `role='admin'` | 2 | DB/PostgreSQL | F1-SEC-03 | `075_audit_remediation.sql` |
| F1-SEC-06 | Ограничить `delete_job_cascade`/`delete_user_cascade` → `service_role` only | 2 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-SEC-07 | Исправить `apply_job_atomic` — убрать двойной инкремент `current_workers` | 3 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-SEC-09 | Добавить проверку владельца в `accept_application`/`reject_application` RPC | 3 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-SEC-10 | Исправить RLS `messages` INSERT — только участники application | 2 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-SEC-12 | Повысить bcrypt rounds до 12, добавить rehash-on-login | 4 | DB/PostgreSQL + Backend | Нет | `auth.py`, `075_audit_remediation.sql` |
| F1-SEC-14 | Исправить `login_required`: `pass` → `session.clear()` + redirect | 1 | Backend Python | Нет | `decorators.py` |
| F1-SEC-17 | Исправить JWT role: использовать реальную роль вместо `'trudnikapp'` | 3 | Backend Python | Нет | `auth.py`, `postgrest_client.py` |
| F1-SEC-18 | Удалить хардкод секретов (`.env`, `amvera.yml`, скрипты) | 4 | DevOps | Нет | `.env`, `amvera.yaml`, `scripts/*.py` |
| F1-SEC-23 | CSRF-токен: заменить `!=` на `hmac.compare_digest` | 1 | Backend Python | Нет | `__init__.py` |
| F1-SEC-24 | Добавить `SET search_path = ''` в `login_user` RPC | 1 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-SEC-25 | Исправить JWT claim mismatch: добавить `user_id` в payload | 2 | Backend Python | Нет | `auth.py` |
| F1-SEC-44 | `/apply/<job_id>` — убрать GET, оставить только POST | 2 | Backend Python | Нет | `applications.py`, `job_detail.html` |
| F1-SEC-45 | Мутирующие эндпоинты — убрать GET (`/cancel-job`, `/restore-job`, `/delete-job`) | 2 | Backend Python | Нет | `jobs.py`, шаблоны |
| F1-DB-01 | Column-level GRANT для `profiles` — исключить чувствительные поля | 2 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-DB-04 | Расширить `jobs.status` CHECK-конструкцию | 1 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-DB-11 | Добавить `SET search_path = ''` во все SECURITY DEFINER функции | 2 | DB/PostgreSQL | Нет | `075_audit_remediation.sql` |
| F1-REF-34 | Исправить `_time_module.timedelta` → `datetime.timedelta` | 1 | Backend Python | Нет | `email_service.py` |
| F1-REF-31 | Создать Celery-задачу `process_notification_outbox` | 4 | Backend Python | F1-REF-30 | `maintenance_tasks.py`, `celery_app.py` |
| F1-REF-30 | Добавить `title` в payload `notification_service.create()` | 1 | Backend Python | Нет | `notification_service.py` |
| F1-PERF-13 | Оптимизировать `role_required`: использовать сессию, не делать DB-запрос каждый раз | 1 | Backend Python | Нет | `decorators.py` |
| F1-PERF-15 | Убрать/сократить `_wait_for_postgrest` из `create_app()` | 1 | Backend Python | Нет | `__init__.py` |
| F1-PERF-20 | Добавить `Cache-Control: public, max-age=86400` для `/uploads/` | 1 | Backend Python | Нет | `__init__.py` |
| F1-PERF-22 | Исправить `get_unread_count()`: `Prefer: count=exact`, `limit=0` | 1 | Backend Python | Нет | `notification_service.py` |
| F1-INF-01 | Dockerfile: `FROM python:3.12-slim` (исправить версию) | 1 | DevOps | Нет | `Dockerfile` |
| F1-INF-02 | Раскомментировать `USER appuser` в Dockerfile | 1 | DevOps | Нет | `Dockerfile` |
| F1-INF-06 | Rate limit → Redis (вместо in-memory) | 4 | Backend Python | Нет | `rate_limit.py`, `redis_client.py` |
| F1-INF-07 | Дневной лимит email → Redis INCR + TTL | 3 | Backend Python | Нет | `email_service.py` |
| F1-INF-08 | Исправить восстановление Redis-соединения (`self._client = None`) | 1 | Backend Python | Нет | `redis_publisher.py` |
| F1-UX-11 | Исправить сохранение навыков при регистрации (comma-separated) | 2 | Frontend + Backend | Нет | `register.html`, `auth.py` |
| F1-UX-13 | Декрементировать `jobs_remaining` при создании задания | 2 | Backend Python | Нет | `jobs.py` |
| F1-UX-14 | Исправить `audit_log` — `session.get('user_id')` вместо `session.get('user')` | 1 | Backend Python | Нет | `admin.py`, `postgrest_client.py` |

### Фаза 2: Тактические улучшения (1-3 месяца) — 45 задач

Рефакторинг, тесты, производительность, подготовка к монетизации.

| ID задачи | Название | Часы | Специалист | Зависимости | Связь с монетизацией |
|-----------|----------|------|------------|-------------|---------------------|
| F2-SEC-04 | RLS: column-level GRANT + запрет INSERT admin | 3 | DB/PostgreSQL | F1-DB-01 | Нет |
| F2-SEC-11 | Ограничить `notifications`/`email_log` INSERT → service_role | 2 | DB/PostgreSQL | Нет | Нет |
| F2-SEC-13 | Добавить CSRF-токены в формы login/register | 3 | Frontend + Backend | Нет | Нет |
| F2-SEC-15 | `admin_required` — добавить DB-перепроверку роли | 2 | Backend Python | Нет | Нет |
| F2-SEC-16 | Rate limit: per-account lockout + fail-closed для login | 4 | Backend Python | F1-INF-06 | Нет |
| F2-SEC-19 | Убрать `PGRST_JWT_SECRET` из debug-логов | 1 | Backend Python | Нет | Нет |
| F2-SEC-20 | Ограничить CORS для WebSocket | 1 | Backend Python | Нет | Нет |
| F2-SEC-26 | XSS: экранировать `raterName` в `job_detail.html` | 1 | Frontend | Нет | Нет |
| F2-SEC-27 | XSS: flash-сообщения через `textContent` | 1 | Frontend | Нет | Нет |
| F2-SEC-28 | XSS: экранировать `s.name` в `admin.html` | 1 | Frontend | Нет | Нет |
| F2-SEC-29 | Исправить no-op escape в `_filter_skills.html` | 1 | Frontend | Нет | Нет |
| F2-SEC-32 | Path traversal: абсолютный путь в `/uploads/` | 1 | Backend Python | Нет | Нет |
| F2-SEC-35 | SW: не кэшировать приватные страницы | 2 | Frontend | Нет | Нет |
| F2-SEC-38 | Ограничить доступ к `/health/postgrest` | 1 | Backend Python | Нет | Нет |
| F2-SEC-39 | `sanitize_postgrest(email)` в auth.py | 1 | Backend Python | Нет | Нет |
| F2-SEC-41 | `delete_subscription()` — добавить `user_id` проверку | 1 | Backend Python | Нет | Нет |
| F2-SEC-42 | `mark_read()` — добавить `user_id` фильтр | 1 | Backend Python | Нет | Нет |
| F2-SEC-43 | WebSocket: исправить JWT-секрет и claim | 2 | Backend Python | F1-SEC-25 | Нет |
| F2-PERF-02 | Исправить пагинацию: фильтры в SQL, не в Python | 8 | Backend Python | Нет | Нет |
| F2-PERF-04 | Кэшировать `inject_application_count` + инвалидация | 3 | Backend Python | F1-INF-07 | Нет |
| F2-PERF-05 | `job_detail` — 1 запрос вместо 5+ через embedded resources | 4 | Backend Python | Нет | Нет |
| F2-PERF-06 | Использовать `cache_for` на справочных данных | 2 | Backend Python | Нет | Нет |
| F2-PERF-08 | Кэшировать справочники (навыки/религии) в Redis | 2 | Backend Python | Нет | Нет |
| F2-PERF-11 | Дашборд админки — 1 RPC вместо 8 запросов | 4 | Backend + DB | Нет | Нет |
| F2-PERF-17 | RPC `recompute_user_rating` вместо Python-расчёта | 3 | DB/PostgreSQL | Нет | Нет |
| F2-PERF-18 | Connection pool для `requests.Session` — увеличить лимиты | 2 | Backend Python | Нет | Нет |
| F2-PERF-26 | Использовать connection pool для `_login_direct_sql` | 2 | Backend Python | Нет | Нет |
| F2-UX-01 | Пагинация на главной и `/workers` | 4 | Frontend + Backend | F2-PERF-02 | Нет |
| F2-UX-04 | Login: поддержка `?next=` параметра | 2 | Backend Python | Нет | Нет |
| F2-UX-05 | После отклика — редирект обратно к заданию | 1 | Backend Python | Нет | Нет |
| F2-UX-06 | `/chat/new/<user_id>` — разрешить для обоих ролей | 2 | Backend Python | Нет | Нет |
| F2-UX-07 | `chat_title` и `chat_subtitle` — передавать имя собеседника | 2 | Backend Python | Нет | Нет |
| F2-UX-10 | Создать шаблоны password-reset | 3 | Frontend + Backend | Нет | Нет |
| F2-UX-12 | Исправить сохранение навыков при редактировании профиля | 2 | Frontend + Backend | Нет | Нет |
| F2-UX-15 | Иконка в пустом состоянии `/workers` | 1 | Frontend | Нет | Нет |
| F2-UX-17 | Страница «Мои отклики» для трудника | 6 | Frontend + Backend | Нет | Нет |
| F2-UX-19 | Навигация: главная страница активна | 1 | Frontend | Нет | Нет |
| F2-UX-21 | Навигация трудника: исправить кнопку «Отклики» | 2 | Frontend + Backend | F2-UX-17 | Нет |
| F2-UX-23 | `userId` в `window.TRUDNIK_CONFIG` | 1 | Backend + Frontend | Нет | Нет |
| F2-MON-01 | PaymentService: интеграция YooKassa | 16 | Backend Python | Нет | **Да** |
| F2-MON-03 | Логика `is_paid` — true только после оплаты | 4 | Backend Python | F2-MON-01 | **Да** |
| F2-MON-07 | Webhook verification — обязательная проверка подписи | 3 | Backend Python | F2-MON-01 | **Да** |
| F2-ARCH-01 | Расщепить `utils.py` на модули | 12 | Backend Python | Нет | Нет |
| F2-ARCH-12 | Унификация WebSocket-архитектуры | 8 | Backend Python | F2-SEC-43 | Нет |
| F2-TST-01 | Базовый тестовый план для критических путей | 8 | QA | F1-* | Нет |
| F2-TST-02 | Unit-тесты для RPC-функций | 8 | QA + Backend | F1-* | Нет |

### Фаза 3: Стратегические изменения (3-6 месяцев) — 30 задач

Полноценная платёжная система, подписки, масштабирование, архитектурные улучшения.

| ID задачи | Название | Часы | Специалист | Зависимости | Связь с монетизацией |
|-----------|----------|------|------------|-------------|---------------------|
| F3-MON-02 | Модель подписок (basic/pro/business) с квотами | 20 | Backend + DB | F2-MON-01 | **Да** |
| F3-MON-04 | Унификация `tariff_key` во всех таблицах | 4 | DB/PostgreSQL + Backend | F3-MON-02 | **Да** |
| F3-MON-05 | `employer_subscriptions` при регистрации | 3 | Backend Python | F3-MON-02 | **Да** |
| F3-MON-09 | Страница `/pricing` с тарифами | 12 | Frontend + Backend | F3-MON-02 | **Да** |
| F3-MON-10 | История платежей для пользователя | 8 | Frontend + Backend | F2-MON-01 | **Да** |
| F3-MON-11 | Feature flags для платных/бесплатных функций | 6 | Backend + DB | F3-MON-02 | **Да** |
| F3-MON-13 | Раскрытие контактов за плату | 8 | Backend Python | F2-MON-01 | **Да** |
| F3-MON-14 | Чеки самозанятого (receipts) | 8 | Backend Python | F2-MON-01 | **Да** |
| F3-ARCH-03 | `ApplicationService` — вынести логику откликов | 12 | Backend Python | F2-ARCH-01 | Нет |
| F3-ARCH-04 | `assert_postgrest_ok` — централизованная обработка ошибок | 4 | Backend Python | Нет | Нет |
| F3-ARCH-07 | Унифицировать отзыв заявки (один механизм) | 4 | Backend Python | F3-ARCH-03 | Нет |
| F3-ARCH-10 | Все проверки ролей через `@role_required` | 6 | Backend Python | Нет | Нет |
| F3-DB-02 | Создать все недостающие RPC (10 шт.) | 20 | DB/PostgreSQL | F1-DB-* | Нет |
| F3-TST-03 | Интеграционные тесты JWT | 6 | QA | F1-SEC-14 | Нет |
| F3-TST-04 | Race condition тесты (Locust) | 8 | QA | F2-PERF-02 | Нет |
| F3-TST-05 | Тесты Path Traversal + SQL Injection | 4 | QA | Нет | Нет |
| F3-TST-06 | Тесты Circuit Breaker | 4 | QA | Нет | Нет |
| F3-TST-07 | E2E тесты: полный цикл трудника и работодателя | 16 | QA | Все F1, F2 | Нет |
| F3-TST-14 | Тесты WebSocket | 6 | QA | F2-ARCH-12 | Нет |
| F3-INF-03 | `HEALTHCHECK` в Dockerfile | 1 | DevOps | Нет | Нет |
| F3-INF-05 | Удалить неиспользуемые зависимости | 1 | DevOps | Нет | Нет |
| F3-INF-10 | Актуализировать CI/CD (GitHub Actions) | 6 | DevOps | Нет | Нет |
| F3-INF-16 | Мониторинг (Prometheus/Grafana) | 16 | DevOps | Нет | **Да** |
| F3-INF-17 | Алертинг для платёжных операций | 8 | DevOps | F3-INF-16 | **Да** |
| F3-INF-20 | `threading.local()` для `requests.Session` | 3 | Backend Python | Нет | Нет |
| F3-DOC-06 | Документ `MONETIZATION.md` | 4 | Архитектор | F3-MON-* | **Да** |
| F3-DOC-05 | Документирование всех RPC-функций | 6 | Архитектор | F3-DB-02 | Нет |
| F3-REF-09 | Колонка `job_id` в `notifications` | 4 | DB/PostgreSQL | Нет | Нет |
| F3-REF-18 | Исправить timezone в `cancel_application` | 1 | Backend Python | Нет | Нет |
| F3-REF-27 | Circuit Breaker: игнорировать 404/400 | 2 | Backend Python | Нет | Нет |

---

## 5. План поддержки монетизации

### 5.1 Изменения в кодовой базе

#### Новые модули

| Модуль | Назначение | Зависимости |
|--------|------------|-------------|
| `app/services/subscription_service.py` | Управление подписками: создание, проверка, продление, смена тарифа | `postgrest_client`, `payment_service` |
| `app/services/billing_service.py` | Биллинг: расчёт стоимости, инвойсы, история платежей | `subscription_service`, `payment_service` |
| `app/blueprints/billing.py` | Вебхуки платёжного шлюза, страница истории платежей | `billing_service` |
| `app/templates/pricing.html` | Страница с тарифами и подключением | Нет |
| `app/templates/payment_history.html` | История платежей пользователя | `billing` |

#### Модификация существующих модулей

| Модуль | Изменения |
|--------|-----------|
| `app/blueprints/auth.py` | При регистрации работодателя — создавать запись в `employer_subscriptions` с `tariff='basic', jobs_remaining=3` |
| `app/blueprints/jobs.py` | `job_new()`: проверка `jobs_remaining > 0`, декремент после создания; `my_jobs_action()`: инкремент при удалении; фильтр `is_paid=eq.true` только при `MONETIZATION_ENABLED=True` |
| `app/blueprints/profile.py` | Отображение текущего тарифа, кнопка «Сменить тариф» |
| `app/context_processors.py` | `inject_employer_subscription`: возвращать реальные данные из `employer_subscriptions` |
| `app/utils/business.py` | Унифицировать `tariff` константы: `BASIC`, `PRO`, `BUSINESS` |

#### Feature Flags

| Флаг | Назначение | Где используется |
|------|------------|-----------------|
| `MONETIZATION_ENABLED` | Глобальное включение монетизации | `config.py`, все blueprints |
| `FEATURE_CONTACT_REVEAL` | Раскрытие контактов за плату | `applications.py` |
| `FEATURE_PRIORITY_LISTING` | Приоритетное размещение заданий | `jobs.py` |
| `FEATURE_VERIFICATION_PREMIUM` | Премиум-верификация работодателей | `admin.py`, `profile.py` |
| `FEATURE_ANALYTICS` | Аналитика для работодателей | `admin.py` |

#### Модель данных для платежей и подписок

```sql
-- Тарифы
CREATE TABLE IF NOT EXISTS tariffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(20) NOT NULL UNIQUE,        -- 'basic', 'pro', 'business'
    name VARCHAR(100) NOT NULL,             -- 'Базовый', 'Pro', 'Бизнес'
    price_monthly INT NOT NULL DEFAULT 0,   -- в копейках
    price_yearly INT NOT NULL DEFAULT 0,
    jobs_limit INT NOT NULL DEFAULT 3,      -- количество заданий
    contact_reveals INT NOT NULL DEFAULT 0, -- раскрытий контактов
    priority_listing BOOLEAN NOT NULL DEFAULT FALSE,
    analytics BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Платёжные транзакции
CREATE TABLE IF NOT EXISTS payment_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(id),
    tariff_id UUID REFERENCES tariffs(id),
    amount INT NOT NULL,                   -- в копейках
    currency VARCHAR(3) NOT NULL DEFAULT 'RUB',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, completed, failed, refunded
    provider VARCHAR(20) NOT NULL,          -- 'yookassa', 'stripe'
    provider_payment_id VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Feature flags
CREATE TABLE IF NOT EXISTS feature_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    flag_key VARCHAR(50) NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT,
    rollout_percentage INT NOT NULL DEFAULT 0,  -- 0-100, для постепенного внедрения
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 5.2 Изменения в инфраструктуре

#### Интеграция платёжного шлюза

| Компонент | Требование |
|-----------|------------|
| **YooKassa** (основной) | `shopId`, `secretKey`, вебхук endpoint `/api/billing/webhook/yookassa` |
| **Stripe** (международный) | `publishableKey`, `secretKey`, вебхук endpoint `/api/billing/webhook/stripe` |
| **PCI DSS** | Платёжные данные НЕ хранятся на сервере — только token/id транзакции; все платежи через iframe/redirect шлюза |
| **HTTPS** | Amvera предоставляет SSL; `Strict-Transport-Security` уже настроен |
| **Idempotency** | Все платёжные запросы с ключом идемпотентности для предотвращения двойных списаний |

#### Мониторинг и алертинг

| Метрика | Инструмент | Порог |
|---------|------------|-------|
| Количество успешных платежей | Prometheus counter | Алерт при падении на 50% за час |
| Количество отказов (failed payments) | Prometheus counter | Алерт при >5% от всех попыток |
| Время ответа платёжного шлюза | Prometheus histogram | Алерт при p95 > 5 сек |
| Баланс необработанных вебхуков | Redis queue length | Алерт при >50 pending |
| Circuit Breaker для платёжного шлюза | Существующий CB | Алерт при OPEN |

### 5.3 Изменения в процессах

#### A/B тестирование платных функций

1. **Feature flags с `rollout_percentage`**: новый тариф или функция включается для X% новых пользователей.
2. **Метрики для сравнения**: конверсия в платный тариф, retention через 7/30 дней, средний чек.
3. **Статистическая значимость**: минимум 1000 пользователей в каждой группе, длительность теста ≥2 недели.

#### Миграция пользователей на платный тариф

1. **Уведомление за 30 дней**: email + push + баннер в приложении.
2. **Льготный период**: первые 14 дней после включения монетизации — бесплатный доступ ко всем функциям.
3. **Специальное предложение**: скидка 50% на первый месяц для ранних пользователей.
4. **Бесплатный тариф**: basic остаётся бесплатным с ограничением 3 задания/мес.

#### Стратегия ценообразования

| Тариф | Цена (₽/мес) | Заданий | Раскрытий контактов | Приоритет | Аналитика |
|-------|-------------|---------|---------------------|-----------|-----------|
| **Базовый** | 0 | 3 | 0 | Нет | Нет |
| **Pro** | 999 | 30 | 30 | Да | Нет |
| **Бизнес** | 2 999 | ∞ | ∞ | Да | Да |

### 5.4 Гарантии для бесплатной версии

#### Функции, которые НИКОГДА не станут платными

| Функция | Причина |
|---------|---------|
| Регистрация и аутентификация | Базовая потребность, must-have |
| Просмотр списка заданий | Социальная миссия платформы |
| Отклик на задание | Ключевой flow трудника |
| Чат между трудником и работодателем | Базовая коммуникация |
| Базовые уведомления (email/push) | Информирование пользователей |
| Базовый профиль | Минимальная функциональность |

#### Архитектурная защита бесплатного опыта

1. **Изоляция платных функций**: каждая платная функция — отдельный feature flag. Отключение одного флага не ломает остальную систему.
2. **Деградация, а не отказ**: при недоступности платёжного шлюза все платные функции считаются бесплатными (graceful degradation).
3. **Отсутствие рекламы**: монетизация через подписки, не через рекламу — бесплатные пользователи не видят рекламы.
4. **Feature flags в коде**: все проверки монетизации сосредоточены в `app/utils/business.py` через единую функцию `is_feature_available(user_id, feature_key)`.

#### Контроль качества для обоих сегментов

1. **Единый набор тестов**: все E2E тесты прогоняются как с `MONETIZATION_ENABLED=True`, так и с `False`.
2. **Мониторинг конверсии**: отслеживание % пользователей, которые переходят с бесплатного на платный тариф (цель: не ниже 5%).
3. **NPS по сегментам**: отдельный замер удовлетворённости для бесплатных и платных пользователей.
4. **Churn rate**: отслеживание оттока в обоих сегментах — если платная функция вызывает отток бесплатных пользователей, она пересматривается.

---

## Итоговое резюме

### Ключевые цифры

| Показатель | Значение |
|------------|----------|
| Проанализировано файлов | 16 (из 20 запрошенных, 8 не найдены) |
| Извлечено рекомендаций | ~280 |
| Категория A (ВНЕДРИТЬ СЕЙЧАС) | 35 |
| Категория B (ОТЛОЖИТЬ) | ~233 |
| Категория C (ОТКЛОНИТЬ) | 12 |
| Фаза 1 задач | 35 (оценка: ~80 человеко-часов) |
| Фаза 2 задач | 45 (оценка: ~200 человеко-часов) |
| Фаза 3 задач | 30 (оценка: ~220 человеко-часов) |

### Команда (рекомендуемый состав)

| Роль | Кол-во | Фокус |
|------|--------|-------|
| Backend Python Developer | 2 | Flask, PostgREST, Celery, Redis |
| Frontend Developer | 1 | Jinja2, Tailwind CSS, Vanilla JS |
| DevOps Engineer | 1 | Docker, CI/CD, мониторинг |
| PostgreSQL / DB Specialist | 1 | Миграции, RLS, RPC |
| QA Engineer | 1 | PyTest, Playwright, E2E |
| Технический архитектор | 0.5 | Координация, ревью |

### Ключевые риски

1. **RLS не работает**: JWT claim mismatch (`sub` vs `user_id`) — RLS-политики полностью обходятся. Критично.
2. **Уведомления не доставляются**: `notification_outbox` без Celery-задачи + `title` не передаётся. Критично.
3. **Email-отправки падают**: `_time_module.timedelta` — AttributeError при Redis. Критично.
4. **Монетизация неработоспособна**: тарифы не синхронизированы, квоты не обновляются, платежи не обрабатываются.
5. **JWK-секреты в репозитории**: нужна срочная смена всех ключей.

---

> **Документ готов к использованию как дорожная карта развития проекта.**
> **Следующий шаг**: выполнить задачи Фазы 1 силами Code mode.
