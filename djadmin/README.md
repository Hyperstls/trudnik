# djadmin — Django-компаньон «Трудник» (фаза 1)

Django 5.2 LTS поверх **той же** БД PostgreSQL: полная админка (замена 6 admin-blueprint'ов
Flask) + публичные read-only страницы. Спецификация и фазы —
[docs/django_migration_prompt.md](../docs/django_migration_prompt.md).

## Что внутри

- `config/` — settings (env- driven: `DATABASE_URL`/`PG*`, `SECRET_KEY`, `WORKER_SITE_URL`…), urls, wsgi
- `core/models.py` — unmanaged-модели всех бизнес-таблиц (схема управляется SQL-миграциями, не Django)
- `core/auth_backend.py` — вход по email+bcrypt из `profiles` (хэши совместимы с Flask/pgcrypto),
  fail-closed: `suspended` / неподтверждённый email → отказ; лок-аут 5 неудач с бэкофом
- `core/admin/` — админка: профили (роль/блокировка/верификация/удаление через RPC
  `delete_user_cascade`, редактор навыков), задания (guard'ы статусов, `delete_job_cascade`,
  bulk ≤ 50), жалобы (`review_complaint`), справочники, site_pages, outbox (retry), аудит
- `core/views.py` — публичные read-only страницы с RLS-паритетом видимости + `/health`, `/ready`
- Роль БД: `trudnik_dj` (миграция `migrations/148_django_admin_role.sql`, BYPASSRLS)

## Локальный запуск

```bash
docker compose up -d db          # Postgres 5433 (+ PostgREST/Redis не нужны)
.venv/Scripts/python.exe -m pip install -r djadmin/requirements.txt
.venv/Scripts/python.exe djadmin/manage.py check
.venv/Scripts/python.exe djadmin/manage.py runserver 8001
# админка: http://127.0.0.1:8001/admin/ — вход профилем с role=admin (profiles.password_hash bcrypt)
```

Локально роль суперюзера docker (`trudnik`) уже BYPASSRLS — миграция 148 не обязательна.

## Тесты (против клона dev-БД: живые триггеры и RPC)

```bash
.venv/Scripts/python.exe scripts/dj_test_clone.py
.venv/Scripts/python.exe djadmin/manage.py test core --keepdb -v 1
```

CI (`django.yml`) гоняет только `check`/`compileall` — без БД; полный прогон — локально/pre-deploy.

## Деплой на Amvera (проект trudnik-dj, регион msk1)

1. (однократно) `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py` — применит 148;
   затем суперпользователем: `ALTER ROLE trudnik_dj LOGIN PASSWORD '<секрет>';`
2. (однократно) Создать проект `trudnik-dj` (Docker) и заполнить его env — список в
   `scripts/dj_deploy.sh` (DATABASE_URL с `trudnik_dj`, SECRET_KEY, ALLOWED_HOSTS, CSRF-origins,
   WORKER_SITE_URL). Через Amvera MCP: `createProject` + `createEnvVars`.
3. `bash scripts/dj_deploy.sh` — push `main-jango → master`, rebuild, логи, health.

⚠️ Ветка `main-jango` с её `amvera.yaml` предназначена ТОЛЬКО проекту `trudnik-dj`.
Не пушьте её в проект `trudnik` (Flask): там собирается корневой `Dockerfile`.

Первый старт контейнера: `collectstatic → migrate (системные таблицы django_*) → gunicorn`.

## Известные ограничения фазы 1

- Пишущие пользовательские флоу (отклики, чат, push, регистрация) остаются на Flask — фаза 2+.
- `/uploads/...` отдаются Flask-сервисом: на страницах djadmin ссылки абсолютизируются
  через `WORKER_SITE_URL`.
- Redis/Celery не используются: сессии админки — в БД (`django_session` в схеме public,
  грантов PostgREST-ролям на системные таблицы Django нет).
