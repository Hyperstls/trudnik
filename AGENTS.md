# AGENTS.md — инструкции для AI-агентов (Kilo и др.)

## Проект «Трудник»
Платформа разовой подработки. Стек и архитектура — см. `.kilocode/rules/` (00–08 + project.md).
ВАЖНО: эти rules загружаются автоматически — сверяйся с ними, не выдумывай версии/факты.

## Верификация кода
- Линтеров/typecheck в репо НЕТ. Проверка — через `pytest` (см. 08_testing_and_verify.md).
- Перед коммитом: `py -m py_compile <изменённые .py>` + `py -m pytest tests -q --ignore=tests/test_job_lifecycle.py`.
- Pre-commit хук `detect-secrets` блокирует коммиты с захардкоженными секретами (никогда не хардкоди PGRST_JWT_SECRET и т.п.).

## Доступы Amvera (мониторинг/деплой)
- **CLI креды хранятся в локальном `.env`** (`.env` в `.gitignore`, НЕ коммитится):
  `AMVERA_USER`, `AMVERA_PASSWORD`, `AMVERA_CLI`.
- Читать оттуда: `Get-Content .env | Select-String 'AMVERA_'`.
- Команды и workflow — см. `.kilocode/rules/06_amvera_deploy.md`.
- ⚠️ НИКОГДА не выводи пароль в лог/коммит/ответ. CLI-команды запускай, подставляя значения из `.env` через переменные, а не инлайн.

## Безопасность
- Секреты (JWT, SECRET_KEY, VAPID_*, SMTP) — только из env. Не логировать, не возвращать клиенту.
- Мутирующие запросы — с CSRF (X-CSRF-Token / form csrf_token).
- Доступ к данным — только через PostgREST/RPC (app/utils/postgrest_client.py). Без ORM/raw-SQL в бизнес-логике.
