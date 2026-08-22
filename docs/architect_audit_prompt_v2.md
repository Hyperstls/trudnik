# Архитектурный аудит «Трудник» — промт v2 (скорректирован по фактическому состоянию кода)

Выступи в роли Principal Software Architect и Tech Lead с глубокой экспертизой в Python, гибридных ASGI/WSGI-деплоях, PostgreSQL/PostgREST, защищённой обработке персональных данных (в т.ч. 152-ФЗ РФ) и проектировании модульных монолитов.

Твоя задача: провести комплексный архитектурный аудит платформы разовой подработки «Трудник». Проанализируй стек и архитектуру на предмет узких мест, рисков масштабируемости, проблем безопасности, соответствия best practices и законодательства РФ о персональных данных.

## ЖЁСТКИЕ ОГРАНИЧЕНИЯ (СТРОГО СОБЛЮДАТЬ)
- **Python**: только 3.12. Категорически запрещено предлагать 3.13/3.14.
- **Доступ к БД**: ORM и raw-SQL в бизнес-логике НЕТ. Весь доступ — строго через PostgREST (HTTP) и RPC (PL/pgSQL SECURITY DEFINER).
  - 🔧 Исключение: self-heal Celery-задача `ensure_postgrest_role_grants` использует psycopg2 (через `DATABASE_ADMIN_URL`) для DDL/GRANT/`ALTER FUNCTION` — это DB-admin, не бизнес-логика.
- **Фронтенд**: только Jinja2 + Tailwind + Vanilla JS. Никакого React/TypeScript.
- **Архитектура**: модульный монолит. Микросервисы не предлагать.

## КОНТЕКСТ ПРОЕКТА И СТЕК (сверено с кодом на дату аудита)

**Backend:** Flask 3.1.3 (WSGI) + FastAPI 0.137.1 (ASGI/WebSocket). Точка входа — `asgi.py` (RouterMiddleware): `websocket`+`lifespan` → FastAPI; `http` → Flask через `a2wsgi.WSGIMiddleware`.
- 🔧 **`WSGIMiddleware(flask_app, workers=15)`** — 15 WSGI-потоков на uvicorn-воркер (НЕ 1). В проде `uvicorn asgi:application --workers 2`. Конкурентность HTTP = 2 воркера × 15 потоков = 30 одновременных Flask-запросов, плюс асинхронный event-loop FastAPI для WS в каждом воркере. Проанализируй адекватность пула потоков под I/O-bound (PostgREST) профиль нагрузки и поведение при блокировке.

**База данных:** прод — PostgreSQL 17.6 + PostGIS (Amvera CloudNativePG, регион msk0/Москва); локально — PostgreSQL 15 + PostGIS 3.4 (docker-compose).
**API-слой:** PostgREST v14 (прод = `trudnik-pr`, marketplace) и **v14 локально** (`postgrest/postgrest:latest`, dev=prod parity после инициативы D1). Различия локал/прод по мажору НЕТ.
- 🔧 **PostgREST v14 и JWT claims (исторический контекст, не активное расхождение):** v14 отдаёт JWT только как `request.jwt.claims` (JSON), а НЕ как индивидуальные GUC `request.jwt.claim.<name>`. Изначально все RLS-политики использовали старый формат и были сломаны. Решено двумя путями, **оба активны одновременно**:
  1. миграция 124 — `pgrst_pre_request()` (SECURITY DEFINER, `SET search_path=pg_catalog`): материализует GUC из JSON до выполнения запроса. `PGRST_DB_PRE_REQUEST=pgrst_pre_request` включён и в проде, и в docker-compose.
  2. миграция 125 — перепись RLS-политик на JSON-экстракцию `(current_setting('request.jwt.claims', true)::json->>'user_id')::uuid`.
  Проанализируй: надёжность pre-request как «костыля» vs канонических политик; риски двойного механизма; что произойдёт, если `pgrst_pre_request` упадёт или будет убран.
- **Мутации:** PL/pgSQL SECURITY DEFINER. 🔧 Конвенция `SET search_path = ''` конфликтует с pgcrypto (`gen_salt`/`crypt`) и PostGIS (`ST_MakePoint` и т.п.) — функции падают. Неоднократные баги: миграции 127 (PostGIS geom), 130 (auth RPC pgcrypto), 131 (delete_user_cascade). Проанализируй паттерн управления `search_path`: стоит ли унифицировать на `SET search_path = pg_catalog, public` + schema-qualified вызовы.

**Инфраструктурная нестабильность:** Amvera CloudNativePG периодически сбрасывает членство ролей (`GRANT ... TO trudnikapp`) и может откатывать последние миграции. Решение — Celery beat-задача `ensure_postgrest_role_grants` (каждые 120с) через psycopg2 (`DATABASE_ADMIN_URL`) восстанавливает: гранты ролей (123), сужение чувствительных колонок profiles (132), RLS внутренних таблиц (133), site_pages (134), политики чтения profiles, RLS-политики в старом формате (125), битый search-триггер (126), auth/cascade RPC search_path (130), delete_user_cascade (131). Использует advisory-lock `pg_try_advisory_lock(42123)` против гонок. Проанализируй устойчивость: DDL во время пиковой нагрузки, гонки при множественных воркерах Celery, гонка «123 пере-выдаёт table-level SELECT → окно до шага 1b (132)».

**Async & Background:** Celery 5.6.3 + Redis 8 (прод) / 7-alpine (лок). DB0 — broker + pubsub; DB1 — result-backend. 6 beat-задач. `drain_notification_outbox` — каждые 10с (чтение таблицы `notification_outbox`).
**Сессии (D5 — ИЗМЕНИЛОСЬ):** **Redis-backed server-side sessions** (`SESSION_TYPE='redis'`, `SESSION_USE_SIGNER=True`, `SESSION_KEY_PREFIX='session:'`). Кука содержит только подписанный session_id. `PERMANENT_SESSION_LIFETIME=3600` (1 час, НЕ 24ч). CSRF — session-based. Ротация session-ID при логине (P0-2, защита от session fixation). Отзыв сессий теперь возможен серверно. Проанализируй:.Single point of failure (Redis), соответствие TTL=1ч целям UX, ttl сессий vs TTL JWT (см. ниже).

**Auth & Security:** bcrypt 12 rounds ($2b$, совместим с pgcrypto `crypt()`). 2 JWT-секрета: `PGRST_JWT_SECRET` (PostgREST) и `WEBSOCKET_JWT_SECRET` (WS; только user_id+jti).
- 🔧 **Access token TTL = 24ч** (`ACCESS_TOKEN_TTL_SECONDS = 24*3600`), хранится в `session['access_token']`. Per-request токены для PostgREST (`get_user_headers`) — короткий TTL 300с. `refresh_access_token` при 401, декодирует старый токен с `verify_exp=False` (обход исторического бага verify_exp). jti проверяется в Redis blacklist (`jti_blacklist:{jti}`). Проанализируй рассогласование: сессия живёт 1ч, JWT — 24ч; можно ли использовать «утёкший» JWT после end-of-session (24ч окно).
- 🔧 **`postgrest_admin_request` (service_role, BYPASSRLS):** защита через `_ADMIN_ALLOWED_PREFIXES` + `_ADMIN_WARN_PREFIXES` (проверка вызывающего модуля). **ВАЖНО: проверка только логирует warning, но НЕ прерывает выполнение** (`postgrest_client.py:584-586`). Реальная защита — RLS. Плюс thread-local `_admin_local.caller` (через `admin_context()`) можно задать произвольно, спуфив caller. Проанализируй: можно ли обойти, насколько это безопасно, нужно ли сделать блокирующим.
- 🔧 **FlaskContextTask** инъектит `_request_id` во все задачи, вызванные из Flask request context; задачи без этого параметра падают. Проверь, корректно ли принимают параметр ВСЕ задачи.

**Frontend:** Jinja2 3.1.6, Tailwind CSS, Vanilla JS, PWA (Service Worker + Web Push VAPID). SW: cache-first для статики, network-first для навигаций; исключения `/admin`, `/logout`, `/verify-email`, `/password-reset`, POST-форм. Известные риски: конфликт SW с Set-Cookie при logout, кэширование 408/503.

**Deploy:** Amvera (Docker, supervisord): uvicorn (2 workers, `--timeout-graceful-shutdown 30`), celery_worker (`--concurrency=4`), celery_beat. Миграции НЕ автоприменяются (entrypoint.sh отключён) — вручную или self-heal.

**Масштаб:** ~29 таблиц (25 бизнес + 4 системных); миграции до #134 (с консолидациями); ~24 SECURITY DEFINER RPC; 19 Blueprints, 13 сервисов.

**Git-гигиена (критично):** в рабочих файлах присутствуют неразрешённые маркеры merge-конфликтов `<<<<<<<`/`=======`/`>>>>>>>` (в т.ч. в `asgi.py`, `maintenance_tasks.py`, миграциях 124–133, `AGENTS.md`, docs/*). `maintenance_tasks.py` содержит дубликат определения `ensure_postgrest_role_grants`. Проанализируй риск деплоя/импорта битого кода и зрелость процесса релизов.

## БЕЗОПАСНОСТЬ ПЕРСОНАЛЬНЫХ ДАННЫХ И 152-ФЗ (ПРИОРИТЕТ АУДИТА)
Особое внимание — защите ПДн пользователей и соответствию 152-ФЗ «О персональных данных»:
- 🔧 **Согласие на обработку ПДн (ст. 9):** поле `profiles.consented_at` проставляется как `datetime.now()` при регистрации (`auth.py:265`) БЕЗ реального чекбокса/потока согласия пользователя. Оцени соответствие ст. 9 (согласие должно быть свободным, конкретным, осознанным и недвусмысленным). Что нужно: явный чекбокс, привязка текста согласия к версии, хранение текста/даты/способа.
- 🔧 **Специальные категории ПДн:** для worker собирается ИНН (12-значный налоговый номер, хранится plaintext `profiles.inn`), религия (`religion_id`). Оцени необходимость минимизации данных (ст. 5), обоснованность сбора ИНН для платформы разовой подработки, риск хранения plaintext.
- 🔧 **Права субъекта ПДн:** право на удаление (ст. 17/right to erasure) реализовано частично — `delete_user_cascade` доступен самопользователю (`profile.py:253`) и админу. Проверь: hard-delete vs анонимизация; удержание ПДн в бэкапах CloudNativePG (retention); журналах; таблице outbox. Право на доступ/копию данных (ст. 14, 15) — **функционал экспорта ПДн отсутствует** (`grep` → 0). Дай рекомендации.
- 🔧 **Резидентность и трансграничная передача (ст. 18, ст. 16):** Amvera msk0 (Москва) — данные в РФ (соответствует). Но `trudnik-pr` (PostgREST) и `trudnik-redis` — marketplace-сервисы: подтверди их регион/локацию. Проверь внешние интеграции (Turnstile/Cloudflare, Yandex Geocoder, SMTP) на трансграничную передачу ПДн и необходимость уведомления Роскомнадзора.
- 🔧 **Хранение и уничтожение (ст. 19, ст. 17 ч.3):** цели/сроки хранения, политика удаления после достижения цели; retention для бэкапов; логи, содержащие ПДн (email в логах auth/SMTP).
- 🔧 **Шифрование (ст. 19 ч.1):** at-rest (CloudNativePG шифрование диска?); in-transit (TLS между uvicorn↔PostgREST, PostgREST↔PG, Celery↔Redis). Учти, что `POSTGREST_URL` внутри кластера может быть `http://`.
- 🔧 **Уведомление об инцидентах (ст. 21.1):** есть ли процесс реагирования и журнал инцидентов (таблица `audit_log`?).
- 🔧 **Категорирование/уровень защищённости (Постановление №1119):** определи уровень защищённости ПДн и достаточность мер (Постановление №683).
- 🔧 **Реквизиты оператора (ст. 18 ч.1):** полнота Политики конфиденциальности, реквизиты оператора, контакт ответственного.

## ЗАДАЧИ АУДИТА
1. **Гибрид WSGI/ASGI:** адекватность 2×(15 WSGI потоков + ASGI loop) под профиль I/O-bound; GIL; блокировки в event-loop при тяжёлых Flask-роутах.
2. **Безопасность PostgREST:** (a) `_ADMIN_ALLOWED_PREFIXES` как **не-блокирующий** аудит — можно ли обойти, нужен ли fail-closed; (b) риски pre-request (124) как механизма при наличии канонических политик (125); (c) унификация `search_path` для SECURITY DEFINER; (d) надёжность self-heal (advisory-lock, DDL в пик, окно уязвимости между шагами 1 и 1b).
3. **Auth/сессии/JWT:** рассогласование TTL сессии (1ч) и JWT (24ч); окно использования утёкшего JWT; `verify_exp=False`.
4. **Celery & Outbox:** дубли/потери в `drain_notification_outbox` (идемпотентность, acks_late, prefetch=1); `FlaskContextTask._request_id` — корректность приёма всеми задачами.
5. **Модульность:** нарушения границ (контроллер → PostgREST напрямую, минуя сервисный слой).
6. **ПДн / 152-ФЗ:** все пункты раздела выше.
7. **Git/релиз-гигиена:** маркеры конфликтов в коммиченных файлах, дубликаты функций, процесс merge/CI.

## ФОРМАТ ВЫДАЧИ
1. **Executive Summary** — оценка зрелости 1–10; 3 преимущества; 3 главных риска.
2. **Критические находки** — для каждой: 📍 Суть · ⚠️ Влияние · 🛠 Решение. Выдели отдельный блок «Соответствие 152-ФЗ».
3. **Action Plan** — 🔴 P0 / 🟡 P1 / 🟢 P2 с конкретными шагами.
4. **Слепые зоны** — 2–3 вещи, не отражённые в этом описании, которые нужно проверить дополнительно.

Начинай анализ.
