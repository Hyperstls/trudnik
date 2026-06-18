# 🔐 GitHub Secrets — Настройка CI/CD для проекта «Трудник»

На этой странице перечислены все секреты (GitHub Secrets), которые необходимо настроить в репозитории GitHub для полноценной работы CI/CD-пайплайнов:
- [`test.yml`](../.github/workflows/test.yml) — Backend, E2E, Accessibility и Нагрузочное тестирование (Locust)
- [`build-apk.yml`](../.github/workflows/build-apk.yml) — Сборка Android APK/AAB (TWA)

---

## Где настроить секреты

1. Перейдите в репозиторий GitHub → **Settings** → **Secrets and variables** → **Actions**
2. Нажмите **New repository secret**
3. Добавьте каждый секрет из таблицы ниже

---

## Таблица секретов

| # | Имя секрета | Назначение | Workflow | Обязательность | Пример значения |
|---|-------------|------------|----------|----------------|-----------------|
| 1 | `SUPABASE_URL` | URL Supabase-проекта (база данных PostgreSQL + API) | `test.yml` (test, locust-test) | ✅ Обязательный | `https://abc123.supabase.co` |
| 2 | `SUPABASE_ANON_KEY` | Анонимный (публичный) API-ключ Supabase для запросов от клиента | `test.yml` (test, locust-test) | ✅ Обязательный | `eyJhbGciOiJIUzI1NiIs...` (длинный JWT-токен) |
| 3 | `SUPABASE_SERVICE_ROLE_KEY` | Сервисный (приватный) API-ключ Supabase с полными правами (только сервер) | `test.yml` (test, locust-test) | ✅ Обязательный | `eyJhbGciOiJIUzI1NiIs...` (длинный JWT-токен) |
| 4 | `SECRET_KEY` | Секретный ключ Flask для подписи сессий и CSRF-токенов | `test.yml` (test, locust-test) | ✅ Обязательный | `супер-длинная-случайная-строка-64-символа` |
| 5 | `DATABASE_URL` | Строка подключения к PostgreSQL для Celery-воркера (используется в Docker Compose) | `test.yml` (test, locust-test) | ✅ Обязательный | `postgresql://user:pass@host:5432/dbname` |
| 6 | `EMPLOYER_EMAIL` | Email тестового аккаунта работодателя для E2E-тестов (вход в систему) | `test.yml` (test, locust-test) | ✅ Обязательный | `employer@trudnik.ru` |
| 7 | `EMPLOYER_PASSWORD` | Пароль тестового аккаунта работодателя | `test.yml` (test, locust-test) | ✅ Обязательный | `securePassword123!` |
| 8 | `WORKER_EMAIL` | Email тестового аккаунта работника (соискателя) для E2E-тестов | `test.yml` (test, locust-test) | ✅ Обязательный | `worker@trudnik.ru` |
| 9 | `WORKER_PASSWORD` | Пароль тестового аккаунта работника | `test.yml` (test, locust-test) | ✅ Обязательный | `securePassword123!` |
| 10 | `VAPID_PRIVATE_KEY` | Приватный ключ VAPID для Web Push-уведомлений (RFC 8292) | `test.yml` (test) | ⚠️ Опциональный | `-----BEGIN PRIVATE KEY-----\nMIGTAgE...` |
| 11 | `VAPID_PUBLIC_KEY` | Публичный ключ VAPID для Web Push-уведомлений | `test.yml` (test) | ⚠️ Опциональный | `BCl7dJ8fQ...` (Base64URL-encoded) |
| 12 | `YANDEX_MAPS_API_KEY` | API-ключ Яндекс.Карт для геокодинга и отображения карт | `test.yml` (test) | ⚠️ Опциональный | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| 13 | `KEYSTORE_PASSWORD` | Пароль для keystore, используемого при сборке Android APK/AAB | `build-apk.yml` | ⚠️ Только для Android-сборки | `androidKeystore123!` |

---

## Подробное описание каждого секрета

### 1. `SUPABASE_URL`
**Источник:** Supabase Dashboard → Project Settings → API → Project URL

URL вашего Supabase-проекта. Используется Flask-приложением для подключения к базе данных PostgreSQL через REST API Supabase.

### 2. `SUPABASE_ANON_KEY`
**Источник:** Supabase Dashboard → Project Settings → API → Project API Keys → `anon public`

Анонимный ключ используется для клиентских запросов. В тестовом окружении передаётся в Flask-приложение и используется для аутентификации запросов к Supabase API с ограниченными правами (Row Level Security).

### 3. `SUPABASE_SERVICE_ROLE_KEY`
**Источник:** Supabase Dashboard → Project Settings → API → Project API Keys → `service_role`

Сервисный ключ с полными правами доступа (обходит RLS). Используется ТОЛЬКО на серверной стороне для административных операций. **Никогда не передавайте этот ключ на клиентскую сторону.**

### 4. `SECRET_KEY`
**Источник:** генерируется один раз (`python -c "import secrets; print(secrets.token_hex(32))"`)

Ключ Flask для криптографической подписи сессий, cookies и CSRF-токенов. Должен быть случайной строкой длиной не менее 64 символов. Используйте один и тот же ключ в локальной разработке (`.env`) и в CI/CD.

### 5. `DATABASE_URL`
**Источник:** Supabase Dashboard → Project Settings → Database → Connection string

Строка подключения к PostgreSQL в формате `postgresql://user:password@host:port/database`. Используется Celery-воркером и Celery Beat для прямого подключения к базе данных (в обход Supabase REST API).

### 6-7. `EMPLOYER_EMAIL` / `EMPLOYER_PASSWORD`
**Источник:** Создайте тестового пользователя в Supabase Auth с ролью `employer`

Учётные данные для входа тестового работодателя. Используются в E2E-тестах Playwright для проверки сценариев создания вакансий, управления заявками и т.д.

### 8-9. `WORKER_EMAIL` / `WORKER_PASSWORD`
**Источник:** Создайте тестового пользователя в Supabase Auth с ролью `worker`

Учётные данные для входа тестового работника (соискателя). Используются в E2E-тестах Playwright для проверки сценариев поиска работы, откликов, чата и т.д.

### 10-11. `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY`
**Источник:** Генерируются один раз через `python -c "from pywebpush import WebPusher; ..."` или через [web-push-codelab](https://web-push-codelab.glitch.me/)

Ключи для Voluntary Application Server Identification (VAPID) согласно RFC 8292. Используются для отправки Web Push-уведомлений через сервис-воркер (`static/sw.js`). Если не настроены, push-уведомления не будут работать, но приложение продолжит функционировать.

### 12. `YANDEX_MAPS_API_KEY`
**Источник:** [Яндекс.Разработчик → JavaScript API и HTTP Геокодер](https://developer.tech.yandex.ru/services/)

API-ключ для геокодирования адресов и отображения карт Яндекс.Карт в интерфейсе. Если не настроен, функциональность карт будет недоступна (геокодинг не работает), но приложение продолжит функционировать.

### 13. `KEYSTORE_PASSWORD`
**Источник:** Придумайте надёжный пароль (мин. 6 символов)

Пароль для Java keystore, используемого при подписи Android APK/AAB в workflow `build-apk.yml`. Нужен только если вы собираете Android-приложение (TWA). Должен быть одинаковым для `storepass` и `keypass`.

---

## Проверка настроек

После добавления всех секретов можно запустить workflow вручную:
1. GitHub → **Actions** → **CI/CD Тестирование** → **Run workflow**
2. Убедитесь, что все шаги выполняются успешно (зелёные индикаторы)
3. Проверьте артефакты тестов (pytest-report, coverage, E2E-отчёты)

---

## Примечания по безопасности

- ⚠️ **Никогда** не добавляйте значения секретов в `.env.example` или в код
- 🔒 Все секреты в GitHub шифруются алгоритмом AES-256 и расшифровываются только во время выполнения workflow
- 📋 При локальной разработке используйте файл `.env` (не коммитьте его — он в `.gitignore`)
- 🔄 При изменении секрета в Supabase (например, перевыпуск ключа) не забудьте обновить соответствующий GitHub Secret
