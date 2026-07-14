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

## [Итерация 2] — 2026-07-10 — Архитектура и высокий приоритет (T25–T46, T49, T61, T65)

### Added
- `@role_required('employer')` на 6 маршрутах favorites (T40).
- `chat_title`/`chat_subtitle` из бэкенда в шаблон чата (T28).
- `success: true` в JSON-ответах `/api/skills` и `/api/religions` (T29).
- `validate_inn_checksum` в `profile.py` update_profile (T49).

### Changed
- `SESSION_COOKIE_SECURE` conditional по `DEPLOYMENT_ENV` (T41).
- `PERMANENT_SESSION_LIFETIME` — единое определение 86400 (T42).
- CSP `connect-src`: `wss://*` → конкретный хост из `WEBSOCKET_PUBLIC_URL` (T65).
- Flash-категория `'error'` → `'danger'` в auth.py и decorators.py (T61).
- `api_save_preference` → `api_update_preferences` (T45).

### Fixed
- Batch-обработчик applications: robust извлечение JSON (AttributeError→500) (T32).
- Фильтр `religion=eq` в workers() удалён (столбец `profiles.religion` дропнут) (T46).
- Удалён вызов несуществующего RPC `get_completed_jobs_between` (T30).

### Removed
- 4 мёртвых модуля: `startup.py`, `payment_gateway.py`, `subscription_service.py`, `feature_flags.py` (T27).
- 2 мёртвых эндпоинта: `/api/search/jobs`, `/api/search/workers` (T26).
- `WTF_CSRF_ENABLED = False` из тестовой конфигурации (T34).
- Дублирующий импорт `safe_redirect` в `favorites.py` (T33).
- Module-level `app = create_app()` в `app/__init__.py` (T25).

## [Итерация 3] — 2026-07-14 — Средний приоритет (T43, T47, T48, T51, T52, T56, T64, T67, T68)

### Added
- `window.getCSRFToken()` в `base.js` (глобальный доступ к CSRF-токену) (T52).
- Jinja-фильтр `format_datetime` отдельно от `format_date` (T48).

### Fixed
- Email PII в логах auth.py: удалён из `log.warning`, замаскирован через `_redact_sensitive` (T64).
- Docstring `hash_password`: «6 раундов» → «12 раундов» (T43).

### Changed
- `text-neutral-400` → `text-neutral-500` в `admin.html` (контрастность) (T56).
- `js-job-act-btn` → `js-job-action` в `my_jobs.html` (унификация) (T51).

### Removed
- `static/css/tailwind.css` (исходный, не используется) (T47).
- `photos:job_photos(*)` из 7 SELECT-запросов (T67).
- `tariff, promoted_until` из SELECT-запроса `jobs.py:134` (T68).
- Локальная `getCSRFToken()` из `favorites.js` (T52).
