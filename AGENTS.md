# AGENTS.md — инструкции для AI-агентов (Kilo, GLM и др.)

## Проект «Трудник»
Платформа разовой подработки. Стек и архитектура — см. `.kilocode/rules/` (00–10 + project.md).
ВАЖНО: эти rules загружаются автоматически — сверяйся с ними, не выдумывай версии/факты.

## Верификация кода
- Линтеров/typecheck в репо НЕТ. Проверка — через `pytest` (см. 08_testing_and_verify.md).
- **Перед коммитом:** `.venv\Scripts\python.exe scripts\pre_deploy_check.py` (0 проблем).
- Затем: `.venv\Scripts\python.exe -m py_compile <изменённые .py>` + `.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/test_job_lifecycle.py`.
- Pre-commit хук `detect-secrets` блокирует коммиты с захардкоженными секретами (никогда не хардкоди PGRST_JWT_SECRET и т.п.).
- Тестовые пароли: `Aa1!aaaa` (низкая энтропия, НЕ флагируется).

## Доступы Amvera (мониторинг/деплой)
- **CLI креды** в локальном `.env` (в `.gitignore`, НЕ коммитится): `AMVERA_USER`, `AMVERA_PASSWORD`, `AMVERA_CLI`.
- **MCP** уже подключён к окружению (Bearer-токен) — предпочитай MCP-Tools (не требуют CLI/логина).
- Slug'и: trudnik (app), trudnik-db (PostgreSQL CNPG), trudnik-pr (PostgREST), trudnik-redis.
- ⚠️ НИКОГДА не выводи пароль в лог/коммит/ответ. CLI-команды — через переменные из `.env`.

## Безопасность
- Секреты (JWT, SECRET_KEY, VAPID_*, SMTP, MAX_BOT_TOKEN, SMARTCAPTCHA_SERVER_KEY) — только из env.
- Капча — Yandex SmartCaptcha (РФ). Turnstile (Cloudflare) и Telegram-верификация отключены 2026-08: 152-ФЗ ст. 12 — исключение трансграничной передачи ПДн (см. docs/rkn_notification_fill.md).
- Мутирующие запросы — с CSRF (X-CSRF-Token / form csrf_token).
- Доступ к данным — только через PostgREST/RPC (app/utils/postgrest_client.py).

## Python окружение
- Версия: 3.12 (Dockerfile: FROM python:3.12-slim). НЕ предлагай 3.13/3.14.
- Venv: `.venv\Scripts\python.exe` (Windows), `python` (CI/Linux).
- Установка: `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.
