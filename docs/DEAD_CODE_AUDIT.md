# Аудит мёртвого кода (Dead Code Audit)

Дата: 2026-08-15 (утилизация: 2026-08-16)
Метод: статический анализ (AST/regex-скан всех `app/**/*.py`, `websocket_server/`, `tests/`, `scripts/`) + ручная верификация каждого кандидата чтением кода.
⚠️ Это отчёт. Перед удалением любого пункта — перепроверить (динамические вызовы, планы развития).

## ✅ УТИЛИЗИРОВАНО 2026-08-16

По итогам аудита удалено (все удаления предварительно перепроверены grep по app/+tests/):

| Что | Детали |
|-----|--------|
| `app/services/job_service.py` — 12 функций | `build_job_query`, `build_worker_query`, `search_jobs`, `search_workers`, `_apply_geo_filters`, `apply_skill_filter`, `apply_distance_filter`, `can_edit_job`, `get_employer_jobs`, `create_job`, `update_job`, `get_job_for_edit`. Файл: 668 → 168 строк. **Важно**: `create_job`/`update_job` вызывали RPC, которых НЕТ в БД (проверено pg_proc) — реальное создание заданий идёт прямым POST /jobs (jobs.py). Примечание: `can_edit_job` из секции POSSIBLY UNUSED — упоминание в test_buttons_backend.py:619 оказалось именем тест-метода, не вызовом; сам тест `test_employer_can_edit_job` НЕ затронут (тестирует UI-флоу /jobs/<id>/edit). Каскадно найдены мёртвыми также build_worker_query/search_workers (первичный аудит их пропустил из-за совпадения имён с locustfile-методами) |
| `app/blueprints/auth.py` | `_generate_jwt` (дубликат app.utils.auth.generate_jwt) + импорты `generate_jwt`, `Config`, `postgrest_request`, `postgrest_rpc` |
| 33 неиспользуемых импорта | Все 17 файлов из секции 1 ниже (3 прохода AST-скрипта) |
| `templates/verify_email.html` | Маршрут /verify-email/<token> только flash+redirect, шаблон не рендерится |

Верификация после удаления: py_compile всех файлов OK, `create_app()` OK (148 маршрутов), pre_deploy_check 0 проблем, полный pytest suite зелёный.

**Остались POSSIBLY UNUSED (решение владельца):** `set_lockout`/`get_lockout` (мёртвая фича C56), `add_to_jti_blacklist` (дубликат), `register_webhooks` (ops-хук), `employer_required`/`worker_required`, `db_pool.*`, `render_captcha_widget`, `send_batch_email_notifications`.

---

## 1. Неиспользуемые импорты (33)

Эвристика: имя из `from X import Y` не встречается в файле вне import-строк. Большинство — остатки рефакторинга.

| Файл | Строка | Имя | Примечание |
|------|--------|-----|------------|
| app/blueprints/admin_dashboard.py | 9 | `session` | |
| app/blueprints/admin_dictionaries.py | 5 | `flash` | |
| app/blueprints/admin_dictionaries.py | 5 | `redirect` | |
| app/blueprints/admin_dictionaries.py | 5 | `url_for` | |
| app/blueprints/admin_verification.py | 5 | `request` | |
| app/blueprints/applications.py | 8 | `postgrest_admin_request` | |
| app/blueprints/applications.py | 9 | `assert_postgrest_ok` | |
| app/blueprints/applications.py | 10 | `notify` | |
| app/blueprints/auth.py | 7 | `Config` | |
| app/blueprints/auth.py | 10 | `postgrest_request` | |
| app/blueprints/auth.py | 10 | `postgrest_rpc` | регистрация через admin_users.py — здесь не нужен |
| app/blueprints/chat.py | 10 | `create_notification` | |
| app/blueprints/jobs.py | 3 | `g` | |
| app/blueprints/jobs.py | 3 | `abort` | |
| app/blueprints/jobs.py | 18 | `notify` | |
| app/blueprints/jobs_api.py | 9 | `current_app` | |
| app/blueprints/notifications.py | 4 | `flash` | |
| app/blueprints/profile.py | 3 | `abort` | |
| app/blueprints/profile.py | 5 | `secure_filename` | |
| app/blueprints/profile.py | 10 | `postgrest_admin_request` | |
| app/blueprints/ratings.py | 4 | `current_app` | |
| app/context_processors.py | 8 | `timedelta` | |
| app/context_processors.py | 8 | `timezone` | |
| app/decorators.py | 8 | `abort` | |
| app/services/job_service.py | 11 | `datetime` | |
| app/services/job_service.py | 11 | `timezone` | |
| app/services/payment_service.py | 16 | `Optional` | |
| app/tasks/celery_app.py | 12 | `Any` | |
| app/utils/business.py | 2 | `timedelta` | |
| app/utils/business.py | 4 | `Dict` | |
| app/utils/business.py | 4 | `Any` | |
| app/utils/geo.py | 4 | `Optional` | |
| app/utils/validators.py | 5 | `_has_sql_injection` | импорт-плейсхолдер к комментарию «используйте has_sql_injection из security» |

Риск удаления: минимальный. Рекомендация: убрать при следующем прикосновении к файлу.

---

## 2. Неиспользуемые функции

Исключены из анализа: route-handlers (`@bp.route`), context_processor/before_request-хуки (верифицировано: `inject_application_count`, `inject_user_role`, `log_static_requests` — ЖИВЫЕ), методы классов, `__init__`.

### Подтверждённо UNUSED (10) — только def, ни одного вызова в app/tests/scripts:

| Файл | Строка | Функция | Причина пометки |
|------|--------|---------|-----------------|
| app/blueprints/auth.py | 59 | `_generate_jwt` | дубликат `app.utils.auth.generate_jwt`; в файле только def |
| app/decorators.py | 274 | `employer_required` | нигде не импортируется/не применяется |
| app/decorators.py | 289 | `worker_required` | нигде не импортируется/не применяется |
| app/services/job_service.py | 194 | `search_jobs` | только def; поиск идёт через jobs.py напрямую |
| app/services/job_service.py | 416 | `apply_distance_filter` | только def |
| app/services/job_service.py | 534 | `get_employer_jobs` | только def |
| app/services/job_service.py | 650 | `get_job_for_edit` | только def |
| app/tasks/email_tasks.py | 245 | `send_batch_email_notifications` | только def; beat не планирует |
| app/utils/captcha.py | 33 | `render_captcha_widget` | только def (заменено на Cloudflare Turnstile) |
| app/utils/db_pool.py | 33, 42 | `get_connection`, `release_connection` | psycopg2-пул — legacy до миграции на PostgREST; см. 01_db_access.md |

### POSSIBLY UNUSED (5) — требуют решения владельца:

| Файл | Строка | Функция | Причина |
|------|--------|---------|---------|
| app/utils/redis_client.py | 46 | `set_lockout` | Account Lockout (C56) не подключён к login-флоу — мёртвая фича |
| app/utils/redis_client.py | 68 | `get_lockout` | то же |
| app/utils/redis_client.py | 91 | `add_to_jti_blacklist` | jti-blacklist реально работает через app/utils/auth.py — это осиротевший дубликат |
| app/blueprints/messenger_verify.py | 219 | `register_webhooks` | ops-точка входа («вызывается один раз после деплоя») — не вызывается кодом; вероятно, вызывается вручную |
| app/services/job_service.py | 486 | `can_edit_job` | в app не вызывается; упоминается ТОЛЬКО в test_buttons_backend.py:619 (тест держит мёртвый код живым) |

Верифицировано как LIVE (исключено из кандидатов): `get_smtp_connection` (email_service.py — вызывается на строках 116, 213).

---

## 3. Неиспользуемые шаблоны (1)

| Шаблон | Причина |
|--------|---------|
| `templates/verify_email.html` | маршрут `/verify-email/<token>` (auth.py:615-628) только flash+redirect, никогда не рендерит этот шаблон |

Верифицировано LIVE: `email/chat_message.html`, `email/notification.html` — рендерятся динамически (`email_tasks.py:121,124` → `email_service.render_template('email/' + name + '.html')`). Partials `_*.html`, `base.html` исключены из анализа по правилам.

---

## 4. Неиспользуемые JS-файлы (0)

Все файлы в `app/static/js/` подключаются в шаблонах через `<script src>` или грузятся динамически другими JS. Мёртвых не найдено.

---

## Summary

| Категория | Найдено | Из них подтверждённо безопасно к удалению |
|-----------|---------|--------------------------------------------|
| Unused imports | 33 | 33 (минимальный риск) |
| Unused functions | 15 | 10 UNUSED + 5 POSSIBLY UNUSED (решение владельца: lockout-фича, дубликат jti, ops-хук register_webhooks, can_edit_job с мёртвым тестом) |
| Unused templates | 1 | 1 (verify_email.html) |
| Unused JS | 0 | 0 |

**Рекомендации:**
1. Безопасная зачистка: 33 импорта + 10 UNUSED-функций + verify_email.html (перед удалением `can_edit_job` — удалить/переписать тест test_buttons_backend.py:619).
2. Продуктовые решения: подключить или удалить lockout-фичу (C56); удалить дубликат `add_to_jti_blacklist`; задокументировать способ вызова `register_webhooks` (CLI-скрипт?).
3. При удалении помнить: pre_deploy_check.py + pytest после каждой партии.
