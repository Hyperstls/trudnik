@rule global deploy ops
Amvera: управление продa «Трудник» через MCP и CLI. Этот файл автозагружается — сверяйся без напоминаний.

## 0. Креды и доступ
- **CLI-креды в локальном `.env`** (`.env` в `.gitignore`, НЕ коммитить): `AMVERA_USER`, `AMVERA_PASSWORD`, `AMVERA_CLI` (по умолчанию `amvera`).
- Читать: `Get-Content .env | Select-String 'AMVERA_'`.
- ⚠️ НИКОГДА не выводи пароль в лог/ответ/коммит. CLI-команды — через переменные из `.env`, не инлайн.
- **MCP** уже подключён к этому окружению (Bearer-токен настроен) — предпочитай MCP-Tools (не требуют CLI/логина).

## 1. Топология продa (Amvera, регион msk0)
| Slug | Тип | Назначение |
|---|---|---|
| `trudnik` | compute | Приложение (Flask+FastAPI, supervisord: uvicorn+celery). |
| `trudnik-db` | cnpg (CloudNativePG) | PostgreSQL 17 + PostGIS. Бэкапы — отдельно (см. 06). |
| `trudnik-pr` | marketplace | **PostgREST v14** (отдельный сервис!) — `PGRST_JWT_SECRET` живёт ЗДЕСЬ И в `trudnik`. |
| `trudnik-redis` | marketplace | Redis 8. |
| `trudnik-pgadmin` | marketplace | pgAdmin (профиль debug). |
- Health продa: `https://trudnik-hyperstls.amvera.io/health` (HTTP 200).

## 2. MCP-Tools (предпочтительный способ, доступен сейчас)
CRUD: `listProjects`, `getProject(slug)`, `createProject`, `deleteProject`.
Тарифы/конфиг: `listTariffs(currency,serviceType)`, `listConfigurations`, `getAmveraConfigTemplate(environment)`.
Файлы: `uploadFiles(slug, fileText/filePath, filename, path)`, `downloadFiles(slug, branch, path, filename)`, `listFiles(slug, path, branch)`, `deleteFiles(slug, files, email, branch)`.
Коммиты/логи: `getCommitHistory(slug, branch, page, size)`, `getBuildLogs(serviceName, query, start, end, limit)`, `getRunLogs(...)`, `getEventLogs(...)`.
Управление: `rebuildProject(slug)`, `restartProject(slug)`, `stopBuild(slug)`, `scaleProject(slug, instances)`, `freezeProject(slug)`.
Env: `listEnvVars(slug, isSecret)`, `createEnvVars(slug, envVarsJson)`, `updateEnvVar(slug, id, name, value, isSecret, type)`, `deleteEnvVar(slug, id)`.
Домены: `listDomains(slug)`, `createDomain(slug, domainName, ingressType, ingressPorts)`, `deleteDomain(slug, id)`.
- envVarsJson формат: `[{"name":"KEY","value":"v","isSecret":true,"type":"RUN"}]` (type: RUN | BUILD).
- ⚠️ `listEnvVars`/`getRunLogs` могут возвращать секретные значения — НЕ выводи их пользователю целиком.

## 3. CLI (если MCP недоступен — другой чат без MCP)
- Установка (Windows — нужен Git bash): `curl -sSL https://raw.githubusercontent.com/amvera-cloud/cli/master/amvera-install.sh | bash -s -- v1.0.5`
- Логин (сессия 24ч): `amvera login --user <u> --password <p>` (креды из `.env`).
- Команды: `amvera -v`, `amvera` (список), `<cmd> -h` (справка).
- Ключевые: `amvera describe project --slug trudnik`, `amvera rebuild --slug trudnik`, `amvera logs {build|run} --slug trudnik`, `amvera env ...` (⚠️ баг v1.2.2 на JSON-парсинге → флаг `dotenv`).
- Регионы MCP: msk0 (Москва) `https://openmcp.msk0.amvera.ru/mcp`, waw0 (Варшава) `https://openmcp.waw0.amvera.ru/mcp`.

## 4. Деплой-воркфлоу (git + rebuild)
- Remotes: `amvera` → `https://git.msk0.amvera.ru/hyperstls/trudnik`; `origin` → GitHub `Hyperstls/trudnik`.
- Amvera деплоит ветку **`master`** (amvera/HEAD → amvera/master).
- Триггер сборки: `git push amvera main:master` (локальный main → amvera/master) ИЛИ `amvera rebuild --slug trudnik` / `rebuildProject`.
- Порядок: тесты локально → `git checkout main && git merge staging` → `git push amvera main:master` → монитор сборки (`getBuildLogs`) → `getRunLogs` → healthcheck.
- Миграции НЕ автоприменяются (entrypoint.sh отключён). Self-heal `ensure_postgrest_role_grants` (beat, 120с) ре-применяет 123/132/133/134/135/136/137 + NOTIFY pgrst 'reload schema'. Для гарантии: `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py` (суперпользователь).
- ⚠️ Ротация `PGRST_JWT_SECRET` = обновить env В ОБОИХ `trudnik` и `trudnik-pr` + рестарт (логаут всех). Координируй синхронно.

## 5. Соглашения/предостережения
- Секреты только через env (Amvera env или `.env`). Не хардкодить, detect-secrets блокирует коммит.
- `DEPLOYMENT_ENV=production` обязывает PGRST_JWT_SECRET, SECRET_KEY, WEBSOCKET_JWT_SECRET, ADMIN_API_TOKEN.
- Изменения schema (DROP/DELETE) — после деплоя кода, потом миграция (04_migrations.md).
