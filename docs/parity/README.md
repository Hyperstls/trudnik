# Parity audit — Flask (`origin/main-flask`) vs Django (`main`)

**Дата:** 2026-10-31
**Эталон Flask:** `origin/main-flask` @ `9b3ed42` (read-only worktree `../trudnik-flask`)
**Django:** `feat/agent-pipeline` @ J034 (`main` @ `3f4aa40` не менялся)
**Статус:** auth/profile — P0/P1 закрыты и задеплоены; jobs/applications — P0/P1 и P2 закрыты и задеплоены.
**Production (2026-11-01):** `1472a7d` (J029–J033), `68a5363` (auth P001–P114), `47f69f3` (J034 SmartCaptcha form-urlencoded); `/health` 200.
**Обновление 2026-10-31:** P0-01…P0-04 исправлены контрактами P001–P004
(verify PASS + functional PASS + pattern PASS), см. [P0_RESULTS.md](P0_RESULTS.md).
P1-01/02/06 исправлены контрактами P101/P102/P106, P1-03/04/11 — P103/P104,
P1-07/08/14 — P107/P108/P114; BUILD-01 — B001; TASKS-01 — T001; P1-12 — P112;
P1-10 ORM-путь — P110; P1-05 — P105. См. [P1_RESULTS.md](P1_RESULTS.md).
P1-13 + DB-default P1-10: dev и production — **65/65**, `email_verified default=false`,
gate OK; процедура и восстановление описаны в [MIGRATION_LEDGER.md](MIGRATION_LEDGER.md).

**Jobs/applications:** аудит, P0/P1 и P2 закрыты контрактами J001–J033
(открытых пунктов нет; P2-04/P2-07/P2-09 — осознанные решения, P2-12 карта n/a) —
см. [JOBS_RESULTS.md](JOBS_RESULTS.md), [AUDIT_JOBS_APPLICATIONS.md](AUDIT_JOBS_APPLICATIONS.md),
[DISCREPANCIES_JOBS.md](DISCREPANCIES_JOBS.md),
[ROUTES_MATRIX_JOBS.md](ROUTES_MATRIX_JOBS.md),
[UI_INVENTORY_JOBS.md](UI_INVENTORY_JOBS.md). Полный `core` — 384 OK.

**Следующая область:** открытых пунктов паритета auth/profile и jobs/applications нет;
осталась финальная приёмка и наблюдение за прод-логами.

**E2E smoke (Docker):** `/jobs`, `/workers`, `/login`, `/register`, `/faq` → 200;
`/privacy`, `/terms`, `/safety` были 404 из-за пустого `site_pages` — исправлено L001
(fallback из legacy-контента, SitePage остаётся override); после фикса 200.
**Режим:** только аудит и проверяемые фиксы; код менялся только через контракты pipeline.
**Ветка:** `feat/agent-pipeline`; `main` — `3f4aa40` без изменений.

## Метод

1. Статическая сверка routes → views → forms → templates.
2. Инвентаризация всех кликабельных элементов (формы, кнопки, ссылки, модалки) по шаблонам.
3. Read-only проверки фактической БД: роли, RLS, RPC-сигнатуры, grants, migration ledger (MCP PostgreSQL).
4. Pattern-review маркеры: XSS (`|safe`, `mark_safe`, `innerHTML`), fail-open, N+1.
5. Runtime contract-проверки (HTTP-коды, RPC от имени пользователя, RLS/IDOR, e2e) —
   **следующая фаза**; в отчёте они перечислены как pending с точными проверками.

## Артефакты

| Файл | Содержание |
|---|---|
| [AUDIT_AUTH_PROFILE.md](AUDIT_AUTH_PROFILE.md) | сводный разбор области, что совпало, что нет |
| [DISCREPANCIES.md](DISCREPANCIES.md) | реестр расхождений: ID, severity, evidence, следующий шаг |
| [ROUTES_MATRIX.md](ROUTES_MATRIX.md) | матрица Flask route → Django route/handler |
| [UI_INVENTORY.md](UI_INVENTORY.md) | кликабельные элементы по страницам |
| [CONTRACT_CHECKS.md](CONTRACT_CHECKS.md) | факты БД/RPC/RLS и очередь contract-проверок |
| [152FZ_DATA_FLOWS.md](152FZ_DATA_FLOWS.md) | ПДн, доступы, риски 152-ФЗ |
| [JOBS_RESULTS.md](JOBS_RESULTS.md) | итоги J001–J058: что закрыто, тесты, остаток |
| [REMAINING_UX.md](REMAINING_UX.md) | остаточный UX/parity backlog: FAQ, фильтр навыков, модалка жалобы |
| [GEO_UX_PRIVACY.md](GEO_UX_PRIVACY.md) | логика карт/геолокации и меры 152-ФЗ |

## Главное (кратко)

- **4 P0:** капча (имя поля `smart-token` vs `smart_token`) ломает регистрацию/сброс в проде;
  документы верификации доступны любому авторизованному; публичный профиль отдаёт `contact`;
  в редактировании профиля снова собирается `religion` (спецкатегория ПДн).
- **14 P1:** упрощённая регистрация (потеряны ИНН/самозанятость/контакт/портфолио/опыт/оплата/навыки),
  отсутствие валидации ИНН/контакта, login без per-IP rate-limit и с in-process lockout,
  in-process cooldown сброса/ресенда, синхронная отправка почты, нет инвалидации сессий при смене
  пароля, нет PDF в верификации, `photo_url`/`avatar_url`, resend уже подтверждённым, fail-open
  `email_verified=true`, fail-open rate-limit, RLS обходится ролью `trudnik_dj` (компенсация —
  queryset-менеджеры, но публичный профиль уже течёт), migration ledger отстаёт от кода,
  удаление аккаунта не чистит файлы ПДн.
- **18 P2:** UX-упрощения (нет удаления фото/логаута на странице профиля, нет чата/отзывов/бейджа
  «надёжный» в публичном профиле), смена URL `/profile/<id>` → `/workers/<id>` без редиректа,
  мёртвые корневые `templates/` от Flask, CSRF 403 вместо дружелюбного редиректа, `|safe` на
  юридических страницах, API prefs POST и др.

## Что дальше

1. Утвердить severity/приоритеты и решение по 152-ФЗ (P0-02/03/04 — блокеры).
2. Сделать контракты на P0 (по одному на расхождение), затем P1.
3. Runtime contract-проверки: капча с валидным токеном, verification-doc owner/other/admin,
   публичный профиль без ПДн, login rate-limit, инвалидация сессий, e2e кликабельных элементов.
4. После стабилизации — docs-актуализация (отдельные контракты) и повторный parity-прогон.
