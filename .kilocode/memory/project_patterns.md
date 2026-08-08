# Паттерны и уроки проекта «Трудник»

Этот файл — постоянная база знаний для GLM/Kilo. Заполнялся по итогам 100+ багфиксов.

## CSP (Content Security Policy)
- Политика: `strict-dynamic` + nonce. Блокирует ВСЕ inline event handlers (onclick, onchange, onsubmit, onload).
- **ПРАВИЛО:** НИКОГДА не используй `onclick=` в HTML. Всегда `id="btn-x"` + `addEventListener` в nonce-скрипте.
- **ПРАВИЛО:** Все `<script>` должны иметь `nonce="{{ csp_nonce }}"`.
- **ИСКЛЮЧЕНИЕ:** `onerror=` на `<img>` допустим (image fallback).

## PostgREST (v14)
- profiles ограничена column-level GRANT (миграция 132). Чтение без `select=` → 401.
- **ПРАВИЛО:** Все `profiles?...` GET-запросы через user-JWT должны иметь `select=<публичные поля>`.
- PATCH/POST обрабатываются автоматически (_normalize_endpoint добавляет select=public).
- Admin (service_role) обходит RLS — select= не нужен.
- Новые RPC невидимы (404 PGRST202) до `NOTIFY pgrst 'reload schema'`. Self-heal делает это автоматически.
- Embedding с несуществующими колонками → 400 (profiles.skills удалён → использовать user_skills).

## Celery + Flask
- **ПРАВИЛО:** В `app/tasks/*.py` НИКОГДА не используй `current_app.logger` — используй `logging.getLogger(__name__)`.
- `current_app` работает только в Flask request-context. В Celery → RuntimeError.

## CSRF
- Глобальная CSRF-защита (middleware.py) проверяет ВСЕ POST/PUT/PATCH/DELETE.
- **ИСКЛЮЧЕНИЯ:** `/messenger/webhook/*` (внешние сервисы без CSRF-токена).
- Безопасность вебхуков: одноразовый Redis-токен (UUID4, TTL 10 мин), не CSRF.

## Service Worker
- SW перехватывает навигацию (network-first). 302-редиректы ломают SW → "Navigation error".
- **ИСКЛЮЧЕНИЯ:** `/admin`, `/logout`, `/verify-email`, `/password-reset`, `/chat`, `/messenger`, `/my-applications`, `/profile`, `/notifications`.
- При изменении списка исключений — bump CACHE_VERSION (v10→v11).

## HTML
- **ПРАВИЛО:** Не дублируй атрибуты (`class="a" class="b"` → браузер игнорирует второй).
- Merge в один: `class="a b"`.

## Amvera Deploy
- Каждый ребилд = 3-5 минут. Локальная проверка = 5 секунд.
- **ПРАВИЛО:** Перед push ВСЕГДА запускай `python scripts/pre_deploy_check.py`.
- При падении CI — проверь Python version (3.12, не 3.11) + Redis service.

## Миграции
- Идемпотентные: `CREATE OR REPLACE`, `IF NOT EXISTS`, `ON CONFLICT`.
- Self-heal применяет 123-138 + NOTIFY pgrst автоматически (каждые 120с).
- SECURITY DEFINER: `SET search_path = pg_catalog, public` (НЕ пустой — ломает pgcrypto/PostGIS).
- RLS: `current_setting('request.jwt.claims', true)::json->>'app_role'` (JSON, не GUC).
