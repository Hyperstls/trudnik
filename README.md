# Трудник — платформа разовой подработки

Соединяет исполнителей (трудников) и заказчиков (работодателей) для разовых задач.

## Стек
- **Backend:** Python 3.12, Flask 3.1 + FastAPI (WebSocket)
- **БД:** PostgreSQL 17 + PostGIS, доступ через PostgREST v14
- **Async:** Celery 5.6 + Redis 8
- **Frontend:** Jinja2 + Tailwind CSS + Vanilla JS
- **Деплой:** Amvera (Docker, регион msk0)

## Структура
```
app/                  # Flask приложение
  blueprints/         # 20 blueprints (auth, jobs, chat, profile, messenger_verify, ...)
  services/           # 13 сервисов (auth, notification, push, email, ...)
  tasks/              # Celery задачи (5 файлов, 7 beat-задач)
  utils/              # PostgREST клиент, auth, валидаторы
websocket_server/     # FastAPI WebSocket сервер
migrations/           # 39 SQL миграций (до #139)
tests/                # pytest (385+ тестов)
tests/manual/         # Standalone CLI скрипты (не в pytest)
docs/                 # Документация
```

## Быстрый старт (локальная разработка)
```bash
# 1. Docker сервисы
docker-compose up -d redis db postgrest

# 2. Python venv
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 3. Тесты
$env:REDIS_URL='redis://:trudnik-local-dev@localhost:6379/0'
.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider --tb=no -q

# 4. Flask dev сервер
docker-compose up web    # HTTP на :8000
```

## Деплой
Деплой на Amvera — через MCP или CLI. См. `.kilocode/rules/06_amvera_deploy.md`.

Health: `https://trudnik-hyperstls.amvera.io/health`

## Документация
- `.kilocode/rules/` — правила проекта (00-10 + project.md)
- `.kilocode/memory/project_patterns.md` — паттерны из 100+ багфиксов
- `docs/` — архитектура, API, безопасность, e2e сценарии
- `scripts/pre_deploy_check.py` — обязательная проверка перед push
