# Трудник — платформа для поиска временной подработки

**Дата:** 2026-06-05
**Статус:** ✅ Миграция с PythonAnywhere на Render

---

## 🚀 Деплой на Render

Проект автоматически деплоится на [Render](https://dashboard.render.com) при каждом `git push` в ветку `main`.

### Первичная настройка на Render

1. Создать новый **Web Service** на [dashboard.render.com](https://dashboard.render.com)
2. Подключить GitHub-репозиторий
3. Настроить параметры:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Добавить переменные окружения в разделе **Environment**:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SECRET_KEY`
   - `YANDEX_MAPS_API_KEY`
   - `DEEPSEEK_API_KEY` (опционально)

Либо используйте файл `render.yaml` из корня проекта для конфигурации через **Blueprint** (Infrastructure as Code).

### После деплоя

1. Render автоматически соберёт и запустит приложение
2. Приложение будет доступно по URL вида `https://trudnik.onrender.com`

---

## 📊 Технологический стек

- **Backend**: Python 3.14 + Flask (Application Factory + Blueprints)
- **База данных**: Supabase (PostgreSQL)
- **Фронтенд**: HTML5 + Tailwind CSS (CDN) + Jinja2
- **Хостинг**: Render (автоматический деплой из GitHub)
- **WSGI-сервер**: Gunicorn

---

## 📚 Документация

Подробная техническая документация проекта доступна в индексном хабе **[TESTING_BLUEPRINT.md](TESTING_BLUEPRINT.md)** и в директории **[docs/](docs/)**:

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

# Запуск
python app.py
```

Приложение будет доступно на `http://localhost:5000`.

---

## 📁 Структура проекта

| Директория/Файл | Назначение |
|-----------------|------------|
| `app.py` | Точка входа |
| `app/` | Основной код (Blueprints, утилиты, конфигурация) |
| `templates/` | HTML-шаблоны (Jinja2) |
| `static/` | Статические файлы (CSS, JS, иконки) |
| `migrations/` | SQL-миграции для Supabase |
| `archive/` | Архив старых скриптов и документации |
| `render.yaml` | Конфигурация деплоя на Render |
| `requirements.txt` | Python-зависимости |

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
# 1. Установка зависимостей (для разработки: pip install -r requirements-dev.txt)
pip install -r requirements.txt

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

### Переменные окружения
| Переменная | Назначение | По умолчанию |
|-----------|-----------|-------------|
| `REDIS_URL` | URL Redis для Pub/Sub и Celery | `redis://localhost:6379/0` |
| `WEBSOCKET_PORT` | Порт WebSocket-сервера | `8001` |
| `SMTP_HOST` | SMTP сервер | `localhost` |
| `SMTP_PORT` | SMTP порт | `587` |
| `VAPID_PRIVATE_KEY` | Приватный VAPID-ключ | — |
| `VAPID_PUBLIC_KEY` | Публичный VAPID-ключ | — |

---

**Готово к деплою на Render! 🎉**
