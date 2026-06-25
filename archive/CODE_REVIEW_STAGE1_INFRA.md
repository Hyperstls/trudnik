# Этап 1: Аудит конфигурации и инфраструктуры

> Дата: 2026-06-22 | Контекст: CODE_REVIEW_CONTEXT.md | Охват: 15 файлов

---

## 1. [app/config.py](app/config.py)

### Найдено проблем: 8

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **HIGH** | SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY указаны в render.yaml:11-16 как envVars, но отсутствуют в Config. Если используются в utils.py, приложение упадёт в runtime. | — | Добавить os.environ.get() с проверкой в production |
| 2 | **HIGH** | DEEPSEEK_API_KEY указан в .env.example:6 и render.yaml:19, но не объявлен в Config. Скрытая зависимость. | — | Добавить DEEPSEEK_API_KEY = os.environ.get() |
| 3 | **MEDIUM** | SESSION_COOKIE_SECURE зависит от FLASK_ENV == production (строка 28). Без установки FLASK_ENV cookie передаются по HTTP — риск перехвата сессии. | 28 | Заменить на FORCE_SECURE_COOKIES или проверять несколько условий |
| 4 | **MEDIUM** | DATABASE_URL (property, 75-94) при отсутствии PG-переменных молча возвращает пустую строку. Код ожидает валидный URL — ошибка без диагностики. | 87-88 | Возвращать None, логировать warning |
| 5 | **MEDIUM** | WORKER_SITE_URL с Amvera-доменом по умолчанию (строка 24). На Render сайт ссылается на неверный URL. | 24 | Сделать обязательной без дефолта |
| 6 | **MEDIUM** | FLASK_ENV устарел (deprecated Flask 2.3+). Семантически неоднозначно: среда Flask vs индикатор платформы. | 15-28 | Заменить на DEPLOYMENT_ENV |
| 7 | **LOW** | load_dotenv() на уровне модуля (строка 4). При импорте до установки env-переменных контейнером — не переопределятся. | 4 | Перенести в create_app() |
| 8 | **LOW** | UPLOAD_FOLDER через os.path.dirname (строка 60). В Docker /data не родитель /app. | 60 | UPLOAD_FOLDER=/data/uploads для Docker |

---

## 2. [app/__init__.py](app/__init__.py)

### Найдено проблем: 10

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **HIGH** | handle_supabase_error (411-421) перехватывает все исключения, пробрасывает не-HTTP через raise e. Неожиданные исключения — стандартный 500 без error.html. | 411-421 | return render_template(error) на 500 для всех не-HTTP |
| 2 | **MEDIUM** | inject_ws_config (154-181) встраивает JWT в HTML с HS256+SECRET_KEY. При XSS — 7-дневный доступ к WebSocket. | 169-177 | Отдельный WEBSOCKET_JWT_SECRET, TTL 1 час |
| 3 | **MEDIUM** | inject_unread_notifications + inject_pending_invitations (183-248) — HTTP-запрос к PostgREST на каждый запрос. При 100 пользователях — 200 запросов/мин только для бейджей. | 183-248 | Кэш в Redis с TTL 30с |
| 4 | **MEDIUM** | handle_supabase_error: только ConnectionError->503. Timeout и HTTPError не перехватываются. | 418 | Добавить Timeout, HTTPError |
| 5 | **MEDIUM** | /health (430) использует postgrest_admin_request. Таймаут БД — health=500, оркестратор перезапустит контейнер. | 434 | try/except + таймаут 5с, всегда возвращать JSON |
| 6 | **MEDIUM** | CSRF отключён при TESTING=True (127). Тесты не валидируют CSRF-защиту. | 127 | Добавить фикстуру csrf_token |
| 7 | **LOW** | get_git_version() — subprocess git log на каждом запросе. В Docker без .git всегда падает. | 48 | Проверять os.path.isdir(.git) |
| 8 | **LOW** | inject_ws_config читает WEBSOCKET_URL/PORT из os.environ вместо app.config. Дублирование источника. | 158-159 | Использовать app.config.get() |
| 9 | **LOW** | log_static_requests логирует каждый статический запрос на INFO. Избыточно. | 385-391 | Понизить до DEBUG |
| 10 | **LOW** | format_date_filter импортирует format_datetime на каждый рендеринг. | 324 | Импорт на уровень модуля |

---

## 3. [app.py](app.py) и [asgi.py](asgi.py)

### Найдено проблем: 6

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **MEDIUM** | app.py:2 создаёт второй экземпляр create_app(). В __init__.py:451 уже есть app = create_app(). Дублирование. | 2 | Удалить app.py или переименовать в wsgi.py |
| 2 | **MEDIUM** | app.py:8 нет защитной проверки от включения debug. | 8 | assert not debug или FLASK_DEBUG проверка |
| 3 | **MEDIUM** | asgi.py:22 logging.warning на каждый WebSocket-запрос — шум в production. | 22 | Понизить до DEBUG или удалить |
| 4 | **MEDIUM** | asgi.py:32 RouterMiddleware без graceful shutdown. WebSocket обрываются без закрытия pub/sub. | 32 | Добавить lifespan shutdown |
| 5 | **LOW** | asgi.py:7 переопределение имени app (Flask) -> ws_app (FastAPI). | 7 | Переименовать в fastapi_app |
| 6 | **LOW** | Порт 8000 (app.py) vs EXPOSE 8000 8001 (Dockerfile) vs CMD --port 80. Три разных порта. | 7 | Задокументировать |

---

## 4. [requirements.txt](requirements.txt) и [requirements-dev.txt](requirements-dev.txt)

### Найдено проблем: 8

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **HIGH** | openai>=2.41.0,<3 — тяжёлая зависимость (~300MB). Не используется согласно документации. | 9 | Удалить |
| 2 | **MEDIUM** | Flask-Login>=0.6.0 — не используется (аутентификация через кастомный декоратор + Supabase JWT). | 2 | Удалить |
| 3 | **MEDIUM** | gunicorn>=23.0.0 — не используется (WSGI через uvicorn). | 6 | Удалить |
| 4 | **MEDIUM** | supabase>=2.30.0 — проект уходит от Supabase (план миграции). Станет мёртвым грузом. | 7 | Пометить TODO |
| 5 | **LOW** | fpdf2>=2.8.0 — не обнаружено использование (чеки для отключённой монетизации). | 8 | Проверить, удалить |
| 6 | **MEDIUM** | Нет верхней границы для pyjwt, cryptography, redis, celery. Риск breaking changes. | 3,11-13,16 | Добавить <N+1 |
| 7 | **LOW** | websockets>=12.0 в dev дублируется с uvicorn[standard]. | 28 | Удалить |
| 8 | **MEDIUM** | python-dotenv импортируется в config.py:2, но не указан явно в requirements.txt. Работает транзитивно. | — | Добавить явно |

---

## 5. [Dockerfile](Dockerfile) и [docker-compose.yml](docker-compose.yml)

### Найдено проблем: 9

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **CRITICAL** | FROM python:3.11-slim — код использует Python 3.12+ (str | None в __init__.py:15). Образ несовместим с кодом. | 1 | python:3.12-slim |
| 2 | **HIGH** | USER appuser закомментирован (строка 34). Контейнер от root в production. Нарушение least privilege. | 34 | Раскомментировать, порт >1024 |
| 3 | **HIGH** | CMD --port 80 — жёстко закодирован. Render задаёт порт через \$PORT. | 38 | --port \${PORT:-80} |
| 4 | **MEDIUM** | docker-compose: --maxmemory-policy allkeys-lru — Redis удаляет Celery-задачи при заполнении. | 12 | noeviction |
| 5 | **MEDIUM** | docker-compose: version: 3.8 устарела (Deprecated в Compose V2). | 1 | Удалить version |
| 6 | **MEDIUM** | docker-compose: отсутствует сервис web (Flask). Flask запускается отдельно. | — | Добавить web: сервис |
| 7 | **MEDIUM** | PGPASSWORD в plain-text в docker-compose. | 42-44 | Docker Secrets для production |
| 8 | **LOW** | celery_worker/beat используют build: . (uvicorn, fastapi не нужны). | 34,62 | Dockerfile.celery |
| 9 | **LOW** | Нет HEALTHCHECK в Dockerfile. | — | Добавить HEALTHCHECK CMD curl /health |

---

## 6. [.env.example](.env.example)

### Найдено проблем: 7

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **HIGH** | Отсутствуют переменные из config.py: FLASK_ENV, TESTING, MAX_PHOTO_SIZE_MB, UPLOAD_FOLDER. | — | Добавить |
| 2 | **HIGH** | Отсутствуют SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY из render.yaml. | — | Добавить секцию Supabase |
| 3 | **HIGH** | Отсутствуют PG-переменные: PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD (нужны для DATABASE_URL). | — | Добавить секцию PostgreSQL |
| 4 | **MEDIUM** | PYTHONANYWHERE_API_TOKEN, PYTHONANYWHERE_USERNAME не используются в config.py. | 16-17 | Удалить или документировать |
| 5 | **MEDIUM** | PGRST_JWT_SECRET=сгенерируйте_через... — предсказуемое значение на русском. | 33 | Заменить на пустое |
| 6 | **LOW** | Нет комментариев с инструкцией получения YANDEX_MAPS_API_KEY, DEEPSEEK_API_KEY. | 5-6 | Добавить ссылки |
| 7 | **LOW** | WEBSOCKET_URL=ws://localhost — для production нужен wss://. Нет комментария. | 13 | Добавить комментарий |

---

## 7. [render.yaml](render.yaml) и [amvera.yml](amvera.yml)

### Найдено проблем: 7

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **CRITICAL** | amvera.yml:7 PGRST_JWT_SECRET=CHANGE_ME — жёстко закодированный placeholder-секрет в Git. Утечка репозитория = скомпрометирован JWT. | 7 | Удалить, задавать через Amvera Secrets |
| 2 | **HIGH** | render.yaml:4 runtime: python — не соответствует (используется Dockerfile, а не buildpack). | 4 | type: docker |
| 3 | **HIGH** | render.yaml:6 buildCommand скачивает tailwindcss бинарник без проверки хеша/подписи. Supply chain риск. | 6 | Добавить sha256sum |
| 4 | **MEDIUM** | amvera.yml неполный: отсутствуют SECRET_KEY, REDIS_URL, POSTGREST_URL, SMTP_*, VAPID_*. | — | Задокументировать для Amvera UI |
| 5 | **MEDIUM** | render.yaml:7 --workers 1 — узкое место. | 7 | --workers 2-4 |
| 6 | **MEDIUM** | amvera.yml: trudnik-celery без command секции. Amvera не узнает как запускать. | 10-12 | Добавить command |
| 7 | **LOW** | render.yaml:5 plan: free — cold-start 50+ сек. | 5 | starter/standard |

---

## 8. [VERSION](VERSION), [.gitignore](.gitignore), [.dockerignore](.dockerignore)

### Найдено проблем: 5

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **HIGH** | .dockerignore:16 комментарий про .git, но !.git отсутствует. get_git_version() всегда падает в Docker -> версия dev. | 16-17 | Добавить !.git |
| 2 | **MEDIUM** | .gitignore:6 и .gitignore:14 дублируется original_app.py. | 6,14 | Удалить дубликат |
| 3 | **LOW** | .gitignore:45-48 uploads/* с исключениями для .gitkeep. Нужно проверить существование .gitkeep. | 45-48 | Проверить файлы |
| 4 | **LOW** | VERSION содержит git log вывод вместо SemVer (MAJOR.MINOR.PATCH). | 1 | Перейти на SemVer |
| 5 | **LOW** | .dockerignore:35 *.md, *.txt кроме requirements — другие .txt тоже исключаются. | 35-37 | Сужение правил |

---

## 9. [pytest.ini](pytest.ini)

### Найдено проблем: 3

| # | Серьёзность | Проблема | Строка | Рекомендация |
|---|------------|----------|--------|--------------|
| 1 | **MEDIUM** | Отсутствует asyncio_mode = auto для pytest-asyncio>=0.21.0. Асинхронные тесты требуют маркер вручную. | — | Добавить asyncio_mode = auto |
| 2 | **LOW** | Нет filterwarnings для подавления DeprecationWarning от supabase, pkg_resources. | — | Добавить filterwarnings |
| 3 | **LOW** | Нет timeout для тестов — зависшие тесты блокируют CI. | — | timeout = 300 |

---

## Сводка по серьёзности

| Серьёзность | Количество |
|-------------|------------|
| **CRITICAL** | 2 |
| **HIGH** | 13 |
| **MEDIUM** | 31 |
| **LOW** | 17 |
| **ВСЕГО** | **63** |

---

## Топ-5 критических проблем

1. **[Dockerfile:1](Dockerfile:1)** — python:3.11-slim вместо python:3.12-slim. Код использует синтаксис Python 3.12+ (str | None в __init__.py:15). Образ несовместим с кодом.
2. **[amvera.yml:7](amvera.yml:7)** — PGRST_JWT_SECRET=CHANGE_ME закоммичен в репозиторий. Секрет в системе контроля версий.
3. **[Dockerfile:34](Dockerfile:34)** — USER appuser закомментирован. Контейнер работает от root в production.
4. **[render.yaml:6](render.yaml:6)** — Скачивание бинарника tailwindcss без проверки хеша/подписи. Supply chain риск.
5. **[.dockerignore:16](.dockerignore:16)** — .git исключён из Docker-образа, но get_git_version() пытается выполнить git log. Версия всегда dev.

---

## Диаграмма несоответствий между файлами

```
config.py          .env.example       render.yaml         amvera.yml
----------         -------------      -----------         ----------
SECRET_KEY    <--  SECRET_KEY    <--  SECRET_KEY     <--  (missing)
SUPABASE_URL  [X]  (missing)     <--  SUPABASE_URL   <--  (missing)
(missing)     [X]  DEEPSEEK_KEY  <--  DEEPSEEK_KEY   <--  (missing)
PGHOST (prop.)[X]  (missing)          (missing)           (missing)
POSTGREST_URL <--  POSTGREST_URL      (missing)      <--  (missing)
                                        PGRST_JWT     <-- PGRST_JWT=CHANGE_ME [!!!]
FLASK_ENV     [X]  (missing)          (missing)      <--  FLASK_ENV=production
```

Легенда: <-- присутствует, [X] отсутствует но должно быть, [!!!] жёстко закодированный секрет

---

## Рекомендация

**NEEDS CHANGES** — 2 CRITICAL и 13 HIGH проблем требуют обязательного исправления перед деплоем в production. Особое внимание:
- Несовместимость версии Python в Dockerfile (3.11 vs 3.12+ в коде)
- Закоммиченный секрет PGRST_JWT_SECRET в amvera.yml
- Отключённый не-root пользователь в контейнере
- Отсутствие критических переменных окружения в .env.example
- Неиспользуемые зависимости (openai, Flask-Login, gunicorn) увеличивают образ и поверхность атаки
