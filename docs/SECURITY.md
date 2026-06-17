# Безопасность — Трудник (Trudnik)

> Многоуровневая система безопасности: аутентификация, CSRF, CSP, Rate Limiting, Circuit Breaker, ролевая модель, RLS.
> **Актуализировано:** 2026-06-17 | **Ветка:** `main`

---

## Аутентификация

### JWT-токены Supabase Auth

Аутентификация построена на **Supabase Auth (GoTrue)**. Используется JWT-пара:

| Токен | Время жизни | Хранение | Назначение |
|-------|-------------|----------|------------|
| `access_token` | Короткое (1 час) | `session['access_token']` | Авторизация запросов к Supabase REST API |
| `refresh_token` | Долгое (30 дней) | `session['refresh_token']` | Обновление access_token без повторного входа |

**Поток аутентификации:**

1. **Логин** (`POST /login`) — пользователь отправляет email/password → Supabase `/auth/v1/token?grant_type=password` → выдаёт JWT-пару
2. **Хранение** — токены сохраняются в серверной сессии Flask (подписанные куки)
3. **Использование** — каждый запрос к Supabase передаёт `Authorization: Bearer <access_token>`
4. **Автообновление** — при 401 или истечении срока, [`refresh_access_token()`](../app/utils.py:277) вызывает `/auth/v1/token?grant_type=refresh_token`

**Регистрация** (`POST /register`):
- Supabase `/auth/v1/signup` создаёт запись в `auth.users`
- Профиль пользователя заполняется через PATCH `profiles` (service_role или токен пользователя)
- Навыки сохраняются через `user_skills` (с валидацией UUID)

**Выход** (`GET /logout`) — полная очистка сессии через `session.clear()`.

**Конфигурация сессионных кук:**
- `SESSION_COOKIE_HTTPONLY = True` — недоступны для JavaScript
- `SESSION_COOKIE_SECURE = True` (на проде) — только по HTTPS
- `SESSION_COOKIE_SAMESITE = 'Lax'` — защита от CSRF на уровне браузера

**Источники:**
- [`app/blueprints/auth.py`](../app/blueprints/auth.py:1)
- [`app/decorators.py:14`](../app/decorators.py:14) — `login_required` с автообновлением
- [`app/utils.py:277`](../app/utils.py:277) — `refresh_access_token()`
- [`app/config.py:17`](../app/config.py:17) — настройки сессионных кук

---

## CSRF-защита

### Глобальный фильтр

Все мутирующие запросы (кроме GET/HEAD/OPTIONS) проходят проверку CSRF-токена через [`@app.before_request`](../app/__init__.py:63):

```python
# Упрощённая логика проверки:
if request.method in ('GET', 'HEAD', 'OPTIONS'):
    return  # Пропуск
if app.config.get('TESTING'):
    return  # Пропуск в тестах
if request.path in ('/login', '/register'):
    return  # Пропуск auth-роутов
```

### Двойная проверка

1. **Заголовок `X-CSRF-Token`** (приоритетный) — для fetch/AJAX-запросов
2. **Поле `_csrf_token`** — в теле формы (`request.form`) или JSON (`request.get_json()`)

При несовпадении → `abort(400, 'CSRF-токен отсутствует или недействителен')`.

### Генерация токена

CSRF-токен генерируется при первом обращении к сессии через [`inject_csrf_token`](../app/__init__.py:26):
```python
session['_csrf_token'] = secrets.token_hex(32)
```
Токен внедряется во все шаблоны как переменная `{{ csrf_token }}`.

### Исключения

- `GET`, `HEAD`, `OPTIONS` — не проверяются
- `/login`, `/register` — не проверяются (на формах нет CSRF-токена)
- Режим `TESTING` — CSRF отключён

---

## CSP (Content Security Policy)

Полная политика безопасности контента задаётся в [`add_security_headers`](../app/__init__.py:42):

```
default-src 'self';
script-src 'self' 'nonce-{random}' https://cdn.jsdelivr.net https://api-maps.yandex.ru https://yastatic.net;
style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com;
img-src 'self' data: https:;
connect-src 'self' https://*.supabase.co https://*.maps.yandex.net https://yastatic.net https://geocode-maps.yandex.ru ws://localhost:* wss://*;
frame-src 'self'
```

### Nonce-механизм

Для каждого запроса генерируется случайный nonce (48 hex-символов) через [`generate_csp_nonce`](../app/__init__.py:37):
```python
g.csp_nonce = secrets.token_hex(24)
```

Nonce внедряется в шаблоны как `{{ csp_nonce }}` и используется для разрешения легитимных inline-скриптов. Все остальные inline-скрипты блокируются.

### Разрешённые внешние источники

| Директива | Внешние источники | Назначение |
|-----------|-------------------|------------|
| `script-src` | `cdn.jsdelivr.net` | Tailwind CSS, внешние библиотеки |
| `script-src` | `api-maps.yandex.ru`, `yastatic.net` | Яндекс.Карты |
| `style-src` | `cdn.jsdelivr.net`, `fonts.googleapis.com` | Стили, шрифты |
| `font-src` | `fonts.gstatic.com` | Google Fonts |
| `connect-src` | `*.supabase.co` | Supabase REST API |
| `connect-src` | `*.maps.yandex.net`, `yastatic.net`, `geocode-maps.yandex.ru` | Яндекс.Карты API |
| `connect-src` | `ws://localhost:*`, `wss://*` | WebSocket-соединения |

### Дополнительные security-заголовки

| Заголовок | Значение | Защита от |
|-----------|----------|-----------|
| `X-Content-Type-Options` | `nosniff` | MIME sniffing |
| `X-Frame-Options` | `DENY` | Clickjacking |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Downgrade-атаки |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Утечка referrer |
| `X-XSS-Protection` | `1; mode=block` | XSS (legacy, дополняет CSP) |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=self` | Доступ к API браузера |

---

## Rate Limiting

### In-memory, per-IP

Декоратор [`@rate_limit`](../app/utils.py:575) ограничивает частоту POST-запросов:

| Параметр | Значение | Источник |
|----------|----------|----------|
| Максимум запросов | **10** | [`Config.RATE_LIMIT_MAX`](../app/config.py:54) |
| Окно | **60 секунд** | [`Config.RATE_LIMIT_WINDOW`](../app/config.py:55) |
| Ключ | IP-адрес (`request.remote_addr`) | |
| Хранилище | In-memory `defaultdict(list)` | |

**Поведение при превышении:**
- AJAX-запросы (`X-Requested-With: XMLHttpRequest` или `Accept: application/json`) → `429 Too Many Requests` с JSON `{"error": "Слишком много попыток. Подождите минуту."}`
- Обычные запросы → flash-сообщение + редирект на `/login`

**Отключение в тестах:** если `app.config['TESTING'] = True`, rate limiting не применяется.

**Где применяется:**
- `POST /login`, `POST /register` — [`auth.py`](../app/blueprints/auth.py:14)
- `POST /apply/<job_id>` — [`applications.py`](../app/blueprints/applications.py:13)
- `POST /api/send_message` — [`chat.py`](../app/blueprints/chat.py:88)
- `POST /api/applications/<id>/accept`, `/reject` — [`app/__init__.py`](../app/__init__.py:273)

---

## Санитизация ввода

### `sanitize_postgrest()`

Все пользовательские параметры, подставляемые в PostgREST-URL, проходят очистку через [`sanitize_postgrest()`](../app/utils.py:619):

**Этапы очистки:**
1. **URL-декодирование** — `%20` → пробел, `%27` → `'` и т.д.
2. **Удаление опасных символов** — `( ) , ; " ' &` (могут изменить структуру PostgREST-запроса)
3. **Экранирование спецсимволов PostgREST** — `.` → `\\.`, `*` → `\\*`
4. **Whitelist-проверка** — удаление всех символов, не входящих в разрешённый набор (кириллица, латиница, цифры, базовые знаки препинания)
5. **Обрезка пробелов** — `.strip()`

**Где используется:**
- Все параметры поиска и фильтрации заданий/трудников
- Параметры URL в админ-панели
- FTS-запросы (`search_vector=fts.russian.{sanitize_postgrest(q)}`)

### XSS в чате

Все сообщения чата проходят санитизацию перед сохранением через [`html.escape()`](../app/blueprints/chat.py:1):
```python
import html as _html
content = _html.escape(content)
```

Дополнительно: максимальная длина сообщения — 2000 символов (серверная валидация).

---

## Circuit Breaker

### Архитектура

Два экземпляра Circuit Breaker для защиты от каскадных отказов при проблемах с Supabase:

| Экземпляр | Назначение | Файл |
|-----------|------------|------|
| `_cb_supabase` | Пользовательские запросы (`supabase_request`, `supabase_rpc`) | [`app/utils.py:100`](../app/utils.py:100) |
| `_cb_admin` | Административные запросы (`supabase_admin_request`, `supabase_rpc` с `use_admin=True`) | [`app/utils.py:101`](../app/utils.py:101) |

### Три состояния

| Состояние | Поведение |
|-----------|-----------|
| **CLOSED** | Нормальная работа, запросы проходят |
| **OPEN** | Цепь разомкнута, запросы не выполняются. Возвращается `SupabaseResponse(ok=False, status_code=503, text='Circuit breaker open')` |
| **HALF_OPEN** | Пробный запрос для проверки восстановления |

### Параметры

| Параметр | Значение |
|----------|----------|
| Порог ошибок (`failure_threshold`) | **5** последовательных ошибок |
| Таймаут восстановления (`recovery_timeout`) | **30 секунд** |

### Потоковая безопасность

Для защиты от race conditions используется `threading.Lock` — все операции изменения состояния (`_record_failure`, сброс счётчика) выполняются под локом.

### Что считается ошибкой

- Исключение при выполнении HTTP-запроса (`requests.RequestException`)
- Ответ с `ok=False` (не 2xx статус)
- `SupabaseResponse` с `ok=False`

**Источник:** [`app/utils.py:29`](../app/utils.py:29) — класс `CircuitBreaker`

---

## Ролевая модель

### Три роли

| Роль | Описание | Типичные права |
|------|----------|----------------|
| **worker** | Трудник | Просмотр заданий, отклики, чат, избранное |
| **employer** | Работодатель | Создание/редактирование заданий, принятие/отклонение откликов, приглашения |
| **admin** | Администратор | Полный доступ: дашборд, управление пользователями, верификация, справочники |

### Декораторы

**`@login_required`** ([`app/decorators.py:14`](../app/decorators.py:14)):
- Проверяет наличие `access_token` в сессии
- При истечении — автоматическое обновление через `refresh_access_token()`
- При неудаче — очистка сессии и редирект на `/login`

**`@role_required(role)`** ([`app/decorators.py:52`](../app/decorators.py:52)):
- Проверяет роль пользователя через запрос к `profiles`
- При несовпадении — flash «Доступ запрещён» и редирект на главную

### Проверка прав в коде

Помимо декораторов, права проверяются явно в обработчиках:
- **Владелец задания** — `check_job_owner()` ([`app/services/job_service.py`](../app/services/job_service.py:1))
- **Владелец отклика** — проверка `worker_id == session['user_id']`
- **Участник чата** — проверка `user_id in (worker_id, employer_id)`
- **Администратор** — проверка роли `session.get('role') == 'admin'`

### RLS (Row Level Security)

На уровне базы данных Supabase все таблицы защищены RLS-политиками. Пользовательские запросы идут с `Authorization: Bearer <access_token>`, и PostgreSQL автоматически ограничивает доступ на основе `auth.uid()`.

**Привилегированные операции** (service_role):
- `supabase_admin_request()` — обходит RLS, используется только на серверной стороне
- Защита: проверка `SERVICE_KEY` перед вызовом ([`_assert_service_key()`](../app/utils.py:217))
- Аудит: логирование всех admin-запросов с указанием вызывающего модуля
- Ограничение контекстов: [`_ADMIN_ALLOWED_PREFIXES`](../app/utils.py:170) — только `app.blueprints`, `app.services`, `app.tasks`, `app.utils`, `scripts`, `tests`
- Предупреждения: вызовы из шаблонов логируются как SECURITY WARNING

**Источники:**
- [`app/decorators.py`](../app/decorators.py:1)
- [`app/utils.py:165`](../app/utils.py:165) — безопасность service_role
- [`migrations/001_setup_rls.sql`](../migrations/001_setup_rls.sql:1)

---

## Сводка уровней защиты

| Уровень | Механизм | Где применяется |
|---------|----------|-----------------|
| **Транспортный** | HTTPS (куки Secure), HSTS | Production-окружение |
| **Аутентификация** | JWT Supabase Auth, автообновление токена | Все запросы |
| **Авторизация** | `@login_required`, `@role_required`, RLS | Маршруты, БД |
| **CSRF** | Глобальный фильтр, двойная проверка (заголовок + тело) | Все мутирующие запросы |
| **XSS** | CSP с nonce, `html.escape()` в чате, санитизация PostgREST | Шаблоны, API, чат |
| **Injection** | `sanitize_postgrest()`, whitelist-проверка | Все параметры PostgREST |
| **Rate Limiting** | In-memory, per-IP, 10 запросов/60 сек | Критические POST-эндпоинты |
| **Устойчивость** | Circuit Breaker (2 экземпляра), 5 ошибок → 30 сек | Все вызовы Supabase |
| **Clickjacking** | `X-Frame-Options: DENY` | Все страницы |
| **MIME sniffing** | `X-Content-Type-Options: nosniff` | Все ответы |
| **Браузерные API** | `Permissions-Policy: camera=(), microphone=(), geolocation=self` | Все страницы |
| **Аудит** | Логирование admin-запросов, caller info | service_role вызовы |
