# Трудник — платформа разовой подработки

Соединяет исполнителей (трудников) и заказчиков (работодателей) для разовых задач.
Публичный прод: **трудник.рф** (`trudnik-hyperstls.msk1.amvera.tech`).

## Стек

- **Backend:** Python 3.12, Django 5.2 (`djadmin/`), ASGI/uvicorn, Channels (WebSocket).
- **БД:** PostgreSQL + PostGIS; Django ходит напрямую через `djadmin/core/rpc.py` (psycopg2, параметризованные запросы), PostgREST остаётся для legacy Flask/интеграций.
- **Async:** Celery + Redis (outbox, письма, периодические задачи).
- **Frontend:** Django templates + Tailwind CSS + vanilla JS/PWA; Yandex Maps и SmartCaptcha (РФ); Android TWA/APK.
- **Деплой:** Amvera, ветка `master`, Dockerfile `Dockerfile.djadmin`.
- **Эталон паритета:** архив Flask — `origin/main-flask` (`9b3ed42`), не рабочий прод.

## Структура

```
djadmin/                    # Django-проект (единственный прод)
  config/                   # settings, urls, asgi/wsgi
  core/
    views*.py               # публичные страницы, auth, профиль, jobs/applications, чат
    forms*.py               # формы и валидаторы
    models.py               # unmanaged-модели поверх существующей БД
    templates/core/         # все актуальные шаблоны (корневые templates/ — legacy Flask)
    tests/                  # 519 тестов (manage.py test core)
  static/                   # собранный Tailwind и JS
migrations/                 # SQL-миграции 067–150+, ledger 65/65
scripts/                    # pre_deploy_check, dj_test_clone, миграции, Amvera
context/agent-pipeline/     # контракты, state, logs, packs (агентный конвейер)
docs/                       # документация: parity, архитектура, UX/UI, 152-ФЗ
templates/                  # legacy Flask (не используется Django)
app/, websocket_server/     # legacy Flask-код (архив)
```

## Быстрый старт

```bash
# 1. Инфраструктура
docker compose up -d db redis

# 2. Python 3.12
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 3. Frontend
npm install
npm run build:css

# 4. Тестовая БД-клон (триггеры/RPC как в dev) и тесты
.venv\Scripts\python.exe scripts\dj_test_clone.py
.venv\Scripts\python.exe djadmin\manage.py test core --keepdb -v 1

# 5. Dev-сервер
.venv\Scripts\python.exe djadmin\manage.py runserver

# 6. E2E критических флоу (Playwright, одноразовые e2e-* данные)
bash scripts/e2e/run_critical_flows.sh

# 7. Restore drill (локальная одноразовая БД, см. docs/RESTORE_DRILL.md)
.venv\Scripts\python.exe scripts/restore_drill.py --drop-target
```

`DJANGO_DB_NAME`, `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `SMTP_*`,
`SMARTCAPTCHA_*`, `YANDEX_MAPS_API_KEY`, `VAPID_*` — только из env/`.env`
(локальный `.env` в `.gitignore`). Никогда не коммитьте значения.

## Обязательные проверки перед коммитом

```bash
npm run build:css
.venv\Scripts\python.exe scripts\pre_deploy_check.py     # 7/7
.venv\Scripts\python.exe -m py_compile <изменённые .py>
.venv\Scripts\python.exe djadmin\manage.py test core --keepdb -v 1
```

Дополнительно: `python djadmin/manage.py check --deploy` с `DEPLOYMENT_ENV=production`
(secure-cookies/HSTS уже настроены; `SECURE_SSL_REDIRECT` — на стороне Amvera).

## Деплой

- Прод собирается из ветки **`master`**; рабочая ветка — `feat/agent-pipeline`, `main` не меняется без релиза.
- Из этой сети `api.msk0`/`git.msk0` недоступны; рабочий путь — `git push amvera-msk1 HEAD:master`
  или MCP (`uploadFiles`/`rebuildProject`/`restartProject`).
- После сборки: `Status: RUNNING`, `/health` 200; при `RUN_PROBLEM` при живом health —
  `restartProject` без пересборки.
- Секреты и доступы — только в env Amvera/`.env`, не в документации.

## Документация

- **Актуальные правила:** [`AGENTS.md`](AGENTS.md), `.kilocode/rules/00–10`.
- **Индекс документации:** [`docs/DOCS_INDEX.md`](docs/DOCS_INDEX.md).
- **Паритет Flask→Django:** [`docs/parity/README.md`](docs/parity/README.md),
  [`JOBS_RESULTS.md`](docs/parity/JOBS_RESULTS.md),
  [`GEO_UX_PRIVACY.md`](docs/parity/GEO_UX_PRIVACY.md).
- **UX/UI-ревью:** [`docs/DESIGN_REVIEW_2026-11.md`](docs/DESIGN_REVIEW_2026-11.md).
- **APK/TWA:** [`docs/APP_RELEASE.md`](docs/APP_RELEASE.md).
- **Агентный конвейер:** [`docs/AGENT_PIPELINE.md`](docs/AGENT_PIPELINE.md),
  `context/agent-pipeline/`.
- **152-ФЗ:** [`docs/rkn_notification_fill.md`](docs/rkn_notification_fill.md),
  [`docs/parity/152FZ_DATA_FLOWS.md`](docs/parity/152FZ_DATA_FLOWS.md).
- **Legacy Flask-документация** (`ARCHITECTURE.md`, `BUSINESS_LOGIC.md`, `API_REFERENCE.md`,
  `FRONTEND.md`, `QA_TEST_CASES.md`, `A11Y_AUDIT.md`, `BUTTON_REGISTRY.md` и др.) —
  исторический снимок Flask-приложения; не является описанием текущего Django-прода.

## Статус

- Полный `core`: **519 OK**, `pre_deploy_check` — 7/7.
- Паритет auth/profile и jobs/applications: открытых пунктов нет (J026 — карта трудников n/a).
- Прод: **RUNNING**, `/health` 200.
