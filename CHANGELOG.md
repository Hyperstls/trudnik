# Changelog

Все заметные изменения проекта «Трудник» по контракту GLM-5.2 (ветка `fix/trudnik-consistency`).

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Итерация 1] — 2026-07-10 — Критичные баги (T1–T24)

### Added
- Шаблоны сброса пароля `templates/password_reset_request.html`,
  `templates/password_reset_confirm.html`; ссылка «Забыли пароль?» в `login.html` (T13).
- `client_message_id` при отправке сообщения в чат (идемпотентность, T10).
- `userId` в `window.TRUDNIK_CONFIG` (T7).
- CSRF-токен (`_csrf_token`) во всех 33 POST-формах (T18).

### Changed
- Маршруты accept/reject/reopen перенесены с объекта `app` на `applications_bp` (T2).
- Префиксы admin-маршрутов: `/admin/job-stats`, `/admin/migrations-status`,
  `/admin/reset-circuit-breaker`, `/admin/health` (T4, T5).
- `change_password` читает `current_password` вместо `old_password` (T20).
- `/logout` — POST-форма + `@rate_limit(fail_open=True)` (T19).
- Минимальная длина пароля — 8 (register/profile); login без minlength (T21).
- Имена env-переменных унифицированы с `.env.example` (T14).
- WebSocket real-time: корректные DOM-id (`messages`, `notifications-list`) (T8).
- Service Worker: заголовок `X-CSRF-Token` (T9).
- Навигация: активные классы по `jobs.index`, убран несуществующий `profile.profile_edit` (T16, T17).

### Fixed
- Кнопка чата некликабельна после batch accept/reject (`shift_id` удалён) (T6).
- `NameError` в `rate_limit_decorator` при ошибке Redis — добавлен `logger` (T11).
- `audit_log.user_id` всегда NULL — неверный ключ сессии `session.get('user')` (T12).
- `sendBeacon('/api/client-error')` проваливал CSRF (text/plain) — теперь `Blob(application/json)` (T15).
- `/api/applications/test` debug-эндпоинт удалён (T3).

### Removed
- Мёртвый `app/blueprints/admin.py` (824 строки, никогда не регистрировался) (T1).
- Неиспользуемый `SENTRY_DSN` из `.env.example` (T14).

### Pending (Phase B/C)
- T22: убрать логирование префикса JWT-секрета. — **DONE** (198364b)
- T23: WS-токен через `/api/ws/token` (убрать `jwtToken` из HTML-источника). — **DONE** (2222eea)
- T24: безопасное включение авто-миграций при деплое. — **DONE** (a02a476)
- T18/T55: `<noscript>` banner вместо fullscreen-overlay. — **DONE** (a20cc77)
- Тесты: password_reset, logout, change_password, log_redaction, ws_token. — **DONE** (239ef72)

### Security (Phase B)
- JWT secret prefix больше не логируется (`auth.py`, `config.py`) (T22).
- WS JWT не встраивается в HTML — выдаётся через `GET /api/ws/token` (T23).
- Миграции применяются при деплое (фильтр NNN, `MIGRATIONS_ENABLED=true`) (T24).
