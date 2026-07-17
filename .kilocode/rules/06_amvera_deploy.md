@rule deploy ops
Деплой и эксплуатация Trudnik на Amvera Cloud (Docker-toolchain).

1. Манифест amvera.yaml:
   - toolchain: docker (сборка по Dockerfile). НЕ python-рантайм Amvera.
   - run: containerPort 8000, servicePort 80, persistenceMount /data.
   - Persistent volume /data: pip-cache, pycache, uploads, celery_beat_data. Изменяемые runtime-файлы пиши ТОЛЬКО под /data.

2. CLI и окружение:
   - Бинарник: env AMVERA_CLI (по умолчанию `amvera`). Все скрипты читают `$AMVERA`.
   - Авторизация: AMVERA_USER / AMVERA_PASSWORD (скрипты вызывают `amvera login`).
   - Slug'и: приложение — `trudnik`; БД — `trudnik-db` (отдельный сервис Amvera, бэкапы — отдельно).

3. Скрипты (scripts/):
   - amvera_full_cycle.sh [slug] [commit-msg] — ОСНОВНОЙ CI/CD: login → describe → git add/commit/push origin main → push amvera (main:master) → rebuild → wait → logs build → logs run → healthcheck.
   - amvera_deploy.sh [slug] — ускоренный: login → rebuild → logs (build 50 / run 30 строк).
   - amvera_env_manager.sh {list|show|add KEY VAL|update|delete KEY|dotenv} [slug] — управление env.
     ⚠️ БАГ CLI v1.2.2: команда `env` падает на парсинге JSON → используй флаг `dotenv` (чтение из локального .env).
   - amvera_db_backup.sh {create|list|delete [backup-id]} [db-slug] — бэкапы PostgreSQL (slug trudnik-db).
   - amvera_monitor.sh [slug] — статус сервисов, тариф, баланс, логи.

4. Ключевые команды CLI:
   - amvera login --user <u> --password <p>
   - amvera rebuild --slug <slug>
   - amvera logs {build|run} --slug <slug>
   - amvera describe project --slug <slug>

5. Git remote `amvera`: `git push amvera main:master` триггерит сборку (альтернатива `amvera rebuild`).

6. Миграции БД: НЕ применяются автоматически при деплое (entrypoint.sh их не запускает).
   Применять вручную ПОСЛЕ деплоя кода:
     MIGRATIONS_ENABLED=true python scripts/apply_migrations.py
   Для BREAKING-изменений схемы: сначала деплой кода (перестал использовать колонку/RPC) → потом миграция (см. 04_migrations.md).

7. Healthcheck: снаружи https://<slug>-hyperstls.amvera.io/health (HTTP 200). Внутри контейнера — /ready (Dockerfile HEALTHCHECK); docker-compose — /health.

8. Секреты (PGRST_JWT_SECRET, WEBSOCKET_JWT_SECRET, SECRET_KEY, ADMIN_API_TOKEN, VAPID_*, SMTP_PASSWORD, YOOKASSA_*) задаются через Amvera env (amvera_env_manager.sh / веб) либо .env. НИКОГДА не коммитить.
