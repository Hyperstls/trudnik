# Безопасность — Трудник (Trudnik)

> Многоуровневая система безопасности: аутентификация, CSRF, CSP, Rate Limiting, Circuit Breaker, ролевая модель, RLS.
> **Актуализировано:** 2026-06-27 | **Ветка:** `main` (миграция с Supabase на Amvera/PostgREST завершена)

---

## Устранённые уязвимости

| # | Уязвимость | Статус |
|---|-----------|--------|
| 1 | **API-ключ DeepSeek в browser_agent.py** — файл перемещён в [`archive/browser_agent.py`](../archive/browser_agent.py), ключ заменён на заглушку | ✅ Устранено |
| 2 | **Хардкоженные пароли в cleanup_extra_users.py** — файл перемещён в [`archive/cleanup_extra_users.py`](../archive/cleanup_extra_users.py) | ✅ Устранено |
| 3 | **Хардкоженные пароли в manage_users.py** — файл перемещён в [`archive/manage_users.py`](../archive/manage_users.py) | ✅ Устранено |
| 4 | **9 утёкших секретов** — задокументированы в [`archive/secret_change.md`](../archive/secret_change.md); требуется верификация чек-листа | ⚠️ Требуется проверка |

---

## Аутентификация

### Нативная аутентификация через PostgREST (Amvera)

Аутентификация построена на **нативных RPC-функциях PostgreSQL** через PostgREST (Amvera).

<!-- УСТАРЕЛО: Ранее использовалась Supabase Auth (GoTrue) -->

| Токен | Время жизни | Хранение | Назначение |
|-------|-------------|----------|------------|
| `access_token` | Короткое (1 час) | `session['access_token']` | Авторизация запросов к PostgREST API |
| `refresh_token` | Долгое (30 дней) | `session['refresh_token']` | Обновление access_token без повторного входа |

**Поток аутентификации:**

1. **Логин** (`POST /login`) — пользователь отправляет email/password → RPC `login_user(p_email, p_password)` → возвращает данные пользователя, Flask генерирует JWT
2. **Хранение** — токены сохраняются в серверной сессии Flask (подписанные куки)
3. **Использование** — каждый запрос к PostgREST передаёт `Authorization: Bearer <access_token>`
4. **Автообновление** — при 401 или истечении срока, [`refresh_access_token()`](../app/utils/postgrest_client.py) обновляет токен

**Регистрация** (`POST /register`):
- RPC `register_user(p_email, p_password, p_full_name, p_role)` создаёт запись в `profiles` с хешированным паролем (**bcrypt 12 раундов**, формат `$2b$`, совместим с pgcrypto `crypt()` — [`app/utils/auth.py`](../app/utils/auth.py))
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
- [`app/utils/postgrest_client.py`](../app/utils/postgrest_client.py) — `refresh_access_token()`
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
connect-src 'self' https://*.amvera.ru https://*.maps.yandex.net https://yastatic.net https://geocode-maps.yandex.ru ws://localhost:* wss://*;
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
| `script-src` | `cdn.jsdelivr.net` | Внешние JS-библиотеки (Tailwind CSS — precompiled локально, `tailwind.min.css`, с CDN **не** грузится) |
| `script-src` | `api-maps.yandex.ru`, `yastatic.net` | Яндекс.Карты |
| `style-src` | `cdn.jsdelivr.net`, `fonts.googleapis.com` | Стили, шрифты |
| `font-src` | `fonts.gstatic.com` | Google Fonts |
| `connect-src` | `*.amvera.ru` | PostgREST API (Amvera) |
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

Декоратор [`@rate_limit`](../app/utils/rate_limit_decorator.py) ограничивает частоту POST-запросов:

| Параметр | Значение | Источник |
|----------|----------|----------|
| Максимум запросов | **10** (дефолт) | env `RATE_LIMIT_MAX_REQUESTS` (app/utils/rate_limit_decorator.py) |
| Окно | **60 секунд** (дефолт) | env `RATE_LIMIT_WINDOW` |
| Ключ | IP-адрес (`request.remote_addr`) | |
| Хранилище | **Redis** (INCR + EXPIRE, Lua-скрипт — атомарно) | fail-open по умолчанию: Redis недоступен → пропуск; `fail_open=False` → отклонение (используется на login/register) |

> 2026-08-21: лимиты конфигурируются через env (дефолты = прод-поведение 10/60с);
> мёртвые ключи `Config.RATE_LIMIT_MAX/WINDOW` удалены из config.py.

**Поведение при превышении:**
- AJAX-запросы (`X-Requested-With: XMLHttpRequest` или `Accept: application/json`) → `429 Too Many Requests` с JSON `{"error": "Слишком много попыток. Подождите минуту."}`
- Обычные запросы → flash-сообщение + редирект на `/login`

**Отключение в тестах:** если `app.config['TESTING'] = True`, rate limiting не применяется.

**Где применяется:**
- `POST /login`, `POST /register` — [`auth.py`](../app/blueprints/auth.py:14)
- Сброс пароля / верификация email / OTP — sensitive-эндпоинты; обязательно проверять наличие `@rate_limit`
- `POST /apply/<job_id>` — [`applications.py`](../app/blueprints/applications.py:13)
- `POST /api/send_message` — [`chat.py`](../app/blueprints/chat.py:88)
- `POST /api/applications/<id>/accept`, `/reject` — [`app/__init__.py`](../app/__init__.py:273)

---

## Санитизация ввода

### `sanitize_postgrest()`

Все пользовательские параметры, подставляемые в PostgREST-URL, проходят очистку через [`sanitize_postgrest()`](../app/utils/security.py):

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

Два экземпляра Circuit Breaker для защиты от каскадных отказов при проблемах с PostgREST (Amvera):

| Экземпляр | Назначение | Файл |
|-----------|------------|------|
| `_cb_postgrest` | Пользовательские запросы (`postgrest_request`, `postgrest_rpc`) | [`app/utils/postgrest_client.py`](../app/utils/postgrest_client.py) |
| `_cb_admin` | Административные запросы (`postgrest_admin_request`, `postgrest_rpc` с `use_admin=True`) | [`app/utils/postgrest_client.py`](../app/utils/postgrest_client.py) |

### Три состояния

| Состояние | Поведение |
|-----------|-----------|
| **CLOSED** | Нормальная работа, запросы проходят |
| **OPEN** | Цепь разомкнута, запросы не выполняются. Возвращается `PostgRESTResponse(ok=False, status_code=503, text='Circuit breaker open')` |
| **HALF_OPEN** | Пробный запрос для проверки восстановления |

### Параметры

| Параметр | Значение |
|----------|----------|
| Порог ошибок (`failure_threshold`) | **10** последовательных ошибок |
| Таймаут восстановления (`recovery_timeout`) | **60 секунд** |

### Потоковая безопасность

Для защиты от race conditions используется `threading.Lock` — все операции изменения состояния (`_record_failure`, сброс счётчика) выполняются под локом.

### Что считается ошибкой

- Исключение при выполнении HTTP-запроса (`requests.RequestException`)
- Ответ с `ok=False` (не 2xx статус)
- `PostgRESTResponse` с `ok=False`

**НЕ считается ошибкой:** HTTP **403** (Forbidden) — это проблема прав/RLS, а не доступности сервиса, и **не размыкает** цепь (см. `_cb_postgrest.call`).

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

**`@role_required(role)`** (legacy; **снят со всех бизнес-действий 2026-09-04 — мультирольность: доступ = владение, не роль**; остаётся только admin_required):
- Проверяет роль пользователя через запрос к `profiles`
- При несовпадении — flash «Доступ запрещён» и редирект на главную

### Проверка прав в коде

Помимо декораторов, права проверяются явно в обработчиках:
- **Владелец задания** — `check_job_owner()` ([`app/services/job_service.py`](../app/services/job_service.py:1))
- **Владелец отклика** — проверка `worker_id == session['user_id']`
- **Участник чата** — проверка `user_id in (worker_id, employer_id)`
- **Администратор** — проверка роли `session.get('role') == 'admin'`

### RLS (Row Level Security)

На уровне базы данных PostgreSQL (Amvera) все таблицы защищены RLS-политиками. Пользовательские запросы идут с `Authorization: Bearer <access_token>` (`role='authenticated'`), и PostgreSQL автоматически ограничивает доступ на основе JWT-claims: `user_id` и `app_role` (`current_setting('request.jwt.claim.app_role', true)` → worker/employer/admin).

<!-- УСТАРЕЛО: Ранее использовался Supabase auth.uid() -->

**Привилегированные операции** (service_role):
- `postgrest_admin_request()` — обходит RLS, используется только на серверной стороне
- Защита: проверка `PGRST_JWT_SECRET` перед вызовом ([`_assert_service_key()`](../app/utils/postgrest_client.py))
- Аудит: логирование всех admin-запросов с указанием вызывающего модуля
- Ограничение контекстов: [`_ADMIN_ALLOWED_PREFIXES`](../app/utils/postgrest_client.py) — только `app.blueprints`, `app.services`, `app.tasks`, `app.utils`, `scripts`, `tests`
- Предупреждения: вызовы из шаблонов логируются как SECURITY WARNING

**Источники:**
- [`app/decorators.py`](../app/decorators.py:1)
- [`app/utils/postgrest_client.py`](../app/utils/postgrest_client.py) — безопасность service_role
- [`migrations/001_setup_rls.sql`](../migrations/archive/001_setup_rls.sql:1)

---

## Безопасность внутренней сети Amvera

⚠️ **Важно:** Amvera не шифрует трафик внутри своей внутренней сети. Все взаимодействие между сервисами внутри платформы (Flask ↔ PostgREST, Flask ↔ Redis, Flask ↔ PostgreSQL) происходит по HTTP, без TLS/SSL.

**Что это означает для проекта:**
- JWT-токены, передаваемые от Flask к PostgREST, идут в открытом виде по внутренней сети
- Service Role Key (PGRST_JWT_SECRET) используется для аутентификации в PostgREST и также передаётся без шифрования
- Данные, передаваемые между преднастроенными сервисами Amvera (PostgREST, Redis, PostgreSQL), не шифруются

**Почему это приемлемо:**
- Внутренняя сеть Amvera изолирована от интернета
- Доступ к внутренним DNS-именам (`amvera-...-run-...`) возможен только из других приложений внутри учётной записи Amvera
- Внешний доступ к приложению обеспечивается через HTTPS (nginx ingress с SSL-сертификатом)

**Рекомендации:**
- Не передавайте конфиденциальные данные между сервисами, если это не необходимо
- Используйте HTTPS для внешних запросов (уже настроено через бесплатный домен Amvera)
- При переходе на собственный домен убедитесь, что SSL-сертификат (Let's Encrypt) корректно привязан

*Источник: документация Amvera, раздел «Сервис доступа»*

---

## Сводка уровней защиты

| Уровень | Механизм | Где применяется |
|---------|----------|-----------------|
| **Транспортный** | HTTPS (куки Secure), HSTS | Production-окружение |
| **Аутентификация** | JWT (нативная аутентификация PostgREST), автообновление токена | Все запросы |
| **Авторизация** | `@login_required`, `@admin_required`, RLS-владение (мультирольность: роль ≠ доступ) | Маршруты, БД |
| **CSRF** | Глобальный фильтр, двойная проверка (заголовок + тело) | Все мутирующие запросы |
| **XSS** | CSP с nonce, `html.escape()` в чате, санитизация PostgREST | Шаблоны, API, чат |
| **Injection** | `sanitize_postgrest()`, whitelist-проверка | Все параметры PostgREST |
| **Rate Limiting** | In-memory, per-IP, 10 запросов/60 сек | Критические POST-эндпоинты |
| **Устойчивость** | Circuit Breaker (2 экземпляра), 10 ошибок → 60 сек | Все вызовы PostgREST (Amvera) |
| **Clickjacking** | `X-Frame-Options: DENY` | Все страницы |
| **MIME sniffing** | `X-Content-Type-Options: nosniff` | Все ответы |
| **Браузерные API** | `Permissions-Policy: camera=(), microphone=(), geolocation=self` | Все страницы |
| **Аудит** | Логирование admin-запросов, caller info | service_role вызовы |
