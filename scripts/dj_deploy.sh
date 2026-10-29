#!/usr/bin/env bash
# Деплой Django-компаньона на Amvera (новый проект trudnik-dj, регион msk1).
#
# Требования:
#   - локальный .env содержит AMVERA_USER, AMVERA_PASSWORD, AMVERA_CLI (по умолчанию amvera)
#   - на Amvera создан проект trudnik-dj (compute, Docker) и в его env заданы:
#       DATABASE_URL=postgresql://trudnik_dj:<секрет>@amvera-hyperstls-cnpg-trudnik-db-rw:5432/trudnik
#       SECRET_KEY=<секрет>          DJANGO_ALLOWED_HOSTS=trudnik-dj-hyperstls.amvera.io
#       CSRF/DJANGO_CSRF_TRUSTED_ORIGINS=https://trudnik-dj-hyperstls.amvera.io
#       WORKER_SITE_URL=https://trudnik-hyperstls.amvera.io
#   - на прод-БД применена миграция 148 и включён вход роли:
#       MIGRATIONS_ENABLED=true DATABASE_ADMIN_URL=... python scripts/apply_migrations.py
#       psql ... -c "ALTER ROLE trudnik_dj LOGIN PASSWORD '<секрет>';"
#
# НЕ пуши эту ветку в проект trudnik (Flask): там собирается корневой Dockerfile.
set -euo pipefail

SLUG="${AMVERA_DJ_SLUG:-trudnik-dj}"
BRANCH="$(git branch --show-current)"
if [ -z "$BRANCH" ]; then
  echo "ОШИБКА: detached HEAD — переключись на ветку (main-jango)." >&2
  exit 1
fi
HEALTH_URL="https://${SLUG}-hyperstls.amvera.io/health"
REMOTE_URL="${AMVERA_DJ_REMOTE:-https://git.msk1.amvera.ru/hyperstls/${SLUG}.git}"
case "$REMOTE_URL" in
  *"$SLUG"*) ;;  # remote обязан указывать на проект SLUG
  *) echo "ОШИБКА: AMVERA_DJ_REMOTE ($REMOTE_URL) не содержит слаг $SLUG." >&2; exit 1;;
esac

# креды из .env (никогда не коммитим и не выводим); локальный .env — CRLF,
# поэтому source через tr -d '\r'
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
set -a
. <(tr -d '\r' < "$SCRIPT_DIR/../.env")
set +a
AMVERA_CLI="${AMVERA_CLI:-amvera}"

echo "==> 1/5 Вход в Amvera CLI"
"$AMVERA_CLI" login --user "$AMVERA_USER" --password "$AMVERA_PASSWORD"

echo "==> 2/5 Git remote ($REMOTE_URL)"
git remote remove dj 2>/dev/null || true
git remote add dj "$REMOTE_URL"

echo "==> 3/5 Push ветки $BRANCH → $SLUG:master"
git push dj "$BRANCH:master" --force

echo "==> 4/5 Rebuild + ожидание сборки"
"$AMVERA_CLI" rebuild --slug "$SLUG" || true
sleep 30
"$AMVERA_CLI" logs build --slug "$SLUG" -n 50 || true

echo "==> 5/5 Логи запуска"
"$AMVERA_CLI" logs run --slug "$SLUG" -n 30 || true

echo "Health: $HEALTH_URL"
for i in $(seq 1 10); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)
  if [ "$code" = "200" ]; then echo "OK: сервис здоров"; exit 0; fi
  echo "  ещё не готов (HTTP $code), ждём 30с…"; sleep 30
done
echo "WARNING: /health не ответил 200 за 5 минут — смотри amvera logs run --slug $SLUG"
exit 1
