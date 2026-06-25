# Трудник — платформа для поиска временной подработки

**Дата:** 2026-06-24
**Статус:** ✅ Развёрнуто на Amvera

---

## 🚀 Деплой на Amvera

Проект деплоится на платформу [Amvera](https://amvera.ru) через конфигурационный файл [`amvera.yaml`](amvera.yaml).

### Первичный деплой

```bash
# Установить CLI (однократно)
pip install amvera

# Залогиниться
amvera login

# Деплой
amvera deploy
```

Конфигурация сборки и запуска описана в [`amvera.yaml`](amvera.yaml).

---

## 📊 Технологический стек

- **Backend**: Python 3.12 + Flask (Application Factory + Blueprints)
- **ASGI-сервер**: Uvicorn
- **База данных**: PostgreSQL + PostgREST
- **Кеш / Брокер**: Redis (Pub/Sub + Celery)
- **Фоновые задачи**: Celery (email, push, maintenance)
- **Деплой**: Amvera (amvera.yaml)

---

## 📁 Структура проекта

| Директория/Файл | Назначение |
|-----------------|------------|
| [`amvera.yaml`](amvera.yaml) | Конфигурация деплоя на Amvera |
| [`Dockerfile`](Dockerfile) | Docker-образ приложения |
| [`docker-compose.yml`](docker-compose.yml) | Локальный стек (Flask + PostgreSQL + Redis + Celery) |
| [`asgi.py`](asgi.py) | Точка входа ASGI (Uvicorn) |
| [`app/`](app/) | Основной код (Blueprints, services, utils, tasks) |
| [`app/templates/`](app/templates/) | HTML-шаблоны (Jinja2) |
| [`app/static/`](app/static/) | Статические файлы |
| [`migrations/`](migrations/) | SQL-миграции для PostgreSQL |
| [`scripts/`](scripts/) | Вспомогательные скрипты |
| [`docs/`](docs/) | Техническая документация |
| [`archive/`](archive/) | Архив старых скриптов и документации |
| [`requirements.txt`](requirements.txt) | Python-зависимости (production) |
| [`requirements-dev.txt`](requirements-dev.txt) | Python-зависимости (development) |

---

## 📚 Документация

| Документ | Содержание |
|----------|-----------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Архитектура, технологический стек, структура проекта |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | Все маршруты и API-эндпоинты |
| [`docs/BUSINESS_LOGIC.md`](docs/BUSINESS_LOGIC.md) | Бизнес-логика, модель данных, жизненные циклы |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Безопасность: JWT, CSRF, CSP, Rate Limiting, RLS |
| [`docs/FRONTEND.md`](docs/FRONTEND.md) | Фронтенд: страницы, JS, UI-компоненты, PWA |
| [`docs/TEST_CHECKLIST.md`](docs/TEST_CHECKLIST.md) | Тестовые сценарии и чеклисты |
| [`docs/E2E_SCENARIOS.md`](docs/E2E_SCENARIOS.md) | End-to-end сценарии по ролям |

---

## 🛠 Локальная разработка

```bash
# Установка production-зависимостей
pip install -r requirements.txt

# Установка всех зависимостей (включая тестовые)
pip install -r requirements-dev.txt

# Запуск полного стека через Docker Compose
docker-compose up -d

# Или запуск Flask-приложения отдельно
python app.py
```

Приложение будет доступно на `http://localhost:5000`.

---

## 🔔 Переменные окружения

Список переменных окружения — в файле [`.env.example`](.env.example). Скопируйте его в `.env` и заполните значениями.

Основные группы переменных:

| Группа | Переменные |
|--------|-----------|
| **Flask** | `SECRET_KEY`, `DEPLOYMENT_ENV` |
| **PostgreSQL / PostgREST** | `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGRST_URL`, `PGRST_JWT_SECRET` |
| **Redis / Celery** | `REDIS_URL`, `CELERY_BROKER_URL` |
| **SMTP / Email** | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` |
| **Внешние API** | `YANDEX_GEOCODER_KEY` |
| **Загрузки** | `UPLOAD_FOLDER`, `MAX_PHOTO_SIZE_MB` |

---

## Система уведомлений v2

Много-канальная система уведомлений реального времени:

### Компоненты
- **WebSocket-сервер** (FastAPI + Redis Pub/Sub) — мгновенная доставка уведомлений и сообщений чата
- **Email-рассылка** (SMTP + Jinja2) — HTML и текстовые шаблоны, пакетная отправка
- **Push-уведомления** (Web Push API + Service Worker) — браузерные уведомления
- **Celery** (Redis брокер) — фоновые задачи для email/push/очистки

### Запуск
```bash
# 1. Установка зависимостей
pip install -r requirements-dev.txt

# 2. Генерация VAPID-ключей (для push-уведомлений)
python -c "from app.utils import generate_vapid_keys; k=generate_vapid_keys(); print(f'VAPID_PRIVATE_KEY={k[0]}\nVAPID_PUBLIC_KEY={k[1]}')"

# 3. Настройка .env (скопируйте .env.example и заполните)
cp .env.example .env

# 4. Запуск Redis (через Docker или локально)
docker run -d --name trudnik-redis -p 6379:6379 redis:7-alpine

# 5. Запуск WebSocket-сервера
uvicorn websocket_server.main:app --host 0.0.0.0 --port 8001

# 6. Запуск Celery воркера
celery -A app.tasks.celery_app worker --loglevel=info

# 7. Запуск Celery Beat (для периодических задач)
celery -A app.tasks.celery_app beat --loglevel=info

# 8. Запуск Flask-приложения
python app.py
```

### Docker Compose (все сервисы)
```bash
docker-compose up -d
```
Сервисы: web, redis, websocket, celery_worker, celery_beat

---

**Готово к деплою на Amvera! 🎉**
