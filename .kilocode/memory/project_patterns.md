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
- **pre_deploy_check (check_profiles_select)** понимает 4 паттерна:
  1. select= прямо в строке вызова.
  2. admin_request / PATCH / POST на текущей ИЛИ предыдущей строке (многострочные вызовы).
  3. Переменная-запрос: `f'profiles?{query}'` где query собрана с select= (`query += '&select=...'`).
  4. Вызов функции-билдера: `query = build_worker_query(...)` где функция содержит select= в теле.
  - select=* ВАЛИДЕН для user-JWT (PostgREST вернёт только разрешённые GRANT'ом колонки).
    401 вызывает лишь ПОЛНОЕ отсутствие select=.

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
- Применение вручную: `MIGRATIONS_ENABLED=true python scripts/apply_migrations.py`.

## Мультирольность (2026-09-04)
- РОЛЬ ≠ ДОСТУП: создавать задания и откликаться может любой пользователь; `role_required` снят со всех бизнес-действий (admin_required остался). Доступ = владение (`job.employer_id == user_id`) / участие.
- ПАТТЕРН БАГА: если добавляешь новый эндпоинт — НЕ ставь role_required; проверяй владение (как invite_worker: check_job_owner).
- `profiles.worker_visibility` (default true): false → скрыт из /workers и не приглашается. Каталог = `worker_visibility=eq.true` (НЕ role=eq.worker).
- Регистрация: `intent` (both/find_work/post_jobs) → role + worker_visibility; RPC `register_user(p_worker_visibility)`.
- Навигация едина для всех ролей; my-applications — табы received/sent.
- Уведомления-бейджи (invitations/applications) считаются для ВСЕХ ролей (context_processors, без role-гейтов).
- Docker-dev: templates/static смонтированы; статика 24ч-кэш → при изменении CSS/JS меняй `?v=` в base.html + bump sw.js CACHE_VERSION.
- Дожато 2026-09: ЧС и каталог работодателей доступны любой роли (гейты `_reject_worker` / `role=eq.employer` сняты; employer_detail = «есть открытые задания»). Полные правила — в AGENTS.md.

## 2026-09: волна UX/качества

### Tailwind-пайплайн
- Исходник `static/css/tailwind.src.css` → `npm run build:css` → `static/css/tailwind.min.css` (коммитится; tailwindcss v3, конфиг `tailwind.config.js`: токены shadow-card/elevated, rounded-card). `node_modules/` в .gitignore.
- **Freshness-гейт:** pre_deploy_check [7/7] сравнивает mtime tailwind.min.css с templates/*.html + static/js/*.js; CI (`test.yml`) делает `npm ci && npm run build:css && git diff --exit-code static/css/tailwind.min.css`. Лечение: `npm run build:css`.
- **ПРАВИЛО:** классы Tailwind — только полными литералами в шаблонах/JS. Динамическую сборку (`'bg-' + color`) сканер не видит → класс не попадёт в CSS.

### Дизайн-система
- Макросы `templates/_components.html`: `btn_primary/btn_secondary/btn_danger/btn_icon`, `status_badge`, `empty_state`, `rating_stars`, `skeleton_block/skeleton_card`. Иконки `_icons.html`: в т.ч. `icon_ban/icon_report/icon_user/icon_bell`.
- Компонентные классы `static/css/app.css`: `.card`, `.form-input/.form-label/.form-hint/.form-error/.form-input-error`, `.text-meta`.
- Формы: единый паттерн «label сверху + .form-input + hint/error»; floating-label удалён. Навыки — `skills-multiselect.js` + `_skills_multiselect.html` (регистрация и профиль).
- Модалки — `<dialog>` только через `showModal()`/`close()` (не display-тоггл, не атрибут open).
- Мобильная шапка: Приглашения/ЧС/Админка — в dropdown `#profile-menu` (aria-menu); бейджи `#notifications-badge` и `#chat-badge` сохранены.
- Cache-busting `?v=20260905` на всей статике в base.html; api.js грузится ДО `{% block scripts %}`; единый showConfirm на `.js-confirm-form` (data-confirm — только источник текста).

### Backend
- `app/services/chat_access.py` (check_participant), `app/services/favorites_service.py` (консолидация избранного 3→1). Удалены: `payment_service.py`, `utils/db_pool.py`, route `/pricing`, `render_captcha_widget`, `EmailService.send_batch(_async)`.
- Миграция 144: `sync_user_skills(p_user_id, p_skill_ids[])` — атомарная замена навыков (регистрация и update_profile). Миграция 145: ratings UNIQUE (rater_user_id, job_id, rated_user_id) + `rate_user_atomic` ON CONFLICT по тройке (работодатель оценивает нескольких исполнителей).
- Приглашения-уведомления фильтруются по `data.type='invitation'` (+fallback подстрока); helper `is_invitation_notification` в notifications.py.
- `/api/ws/token` — 503 без WEBSOCKET_JWT_SECRET (fail-closed, БЕЗ fallback на SECRET_KEY).
- postgrest_client: retry GET (1 доп. попытка, backoff 0.2–0.5с jitter) при 5xx/timeout; убран sleep(0.5) при 401-ретрае; admin-RPC через `_admin_session`.
- Новые JSON endpoint'ы: `POST /api/jobs/<job_id>/apply` и `/unapply` (200/400/403/404/409/503, ответ с my_app_status). `/api/send_message` — 400 при невалидном теле; ответ {status, message_id, created_at}.
- Серверные фильтры каталога: `GET /?filter=new|applied`. Фильтр навыков в /my-applications: sent — по навыкам задания, received — по навыкам откликнувшегося.
- Политика паролей едина: login без minlength-подсказки, смена пароля 8+ (validate_password везде).

### Ловушки тестов
- Mock PostgREST АКТИВЕН в suite: гейт `POSTGREST_MOCK_MODE in ('1','true','yes')`; `_install_auth_mock` вызывается в КОНЦЕ app/utils/__init__ (circular import устранён). Патчить postgrest на уровне blueprint — тоже легально. CB-тесты skipif при активном mock (by design).
- e2e (Playwright): CSP запрещает `wait_for_function`/eval → используй `wait_for_selector`; против optimistic-detach — `dispatch_event('click')`.
- bcrypt `$2b$` (прод PG17) НЕ работает в локальном pgcrypto (PG15 Alpine — только `$2a$`); для локальных тестовых паролей — replace префикса.
- Flask dev-server (bind-mount) может отдавать устаревшие шаблоны → `docker compose restart web` перед e2e/live-прогоном.
- Live-ожидания: `/login` на блокировку — 200+flash (НЕ 429); `/jobs/<invalid>` → 302+flash «Задание не найдено» (не 404); `/api/search/*` не существует (поиск — SSR на /); `/api/religions` 404 by design (спецкатегория ПДн); health — `/health` (не /api/health); own id — из `/profile/export-data`.
