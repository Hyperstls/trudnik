#!/usr/bin/env bash
# Local critical-path E2E runner (J133).
# Starts Django on an isolated port with captcha/email/maps disabled,
# seeds disposable e2e-* data, runs Playwright, then always cleans up.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-.venv/Scripts/python.exe}"
if [ ! -x "$PY" ]; then
  PY="python"
fi

export DJANGO_CAPTCHA_DISABLED=1
export SMARTCAPTCHA_CLIENT_KEY=""
export SMARTCAPTCHA_SERVER_KEY=""
export SMTP_HOST=""
export TRANSACTIONAL_EMAIL_ASYNC=0
export YANDEX_MAPS_API_KEY=""
export YANDEX_GEOCODER_KEY=""
export REDIS_URL=""
export DJANGO_DEBUG=1
# Playwright opens many pages/assets in <60s; keep the per-IP limiter out of E2E.
export GLOBAL_RATE_LIMIT_PER_MIN=10000

LOG="${TMPDIR:-/tmp}/trudnik-e2e-server.log"
"$PY" djadmin/manage.py e2e_seed
"$PY" djadmin/manage.py runserver 127.0.0.1:8801 --noreload >"$LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  "$PY" djadmin/manage.py e2e_seed --cleanup >/dev/null 2>&1 || true
}
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8801/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -fsS http://127.0.0.1:8801/health >/dev/null 2>&1; then
  echo "Django did not start; see $LOG" >&2
  tail -n 50 "$LOG" >&2 || true
  exit 1
fi

E2E_BASE_URL="http://127.0.0.1:8801" node scripts/e2e/critical_flows.mjs
