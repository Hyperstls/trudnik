# Parity audit — Flask (`origin/main-flask`) vs Django (`main`)

**Дата:** 2026-11-01
**Эталон Flask:** `origin/main-flask` @ `9b3ed42` (read-only worktree `../trudnik-flask`)
**Django:** `feat/agent-pipeline` @ J063 (`main` @ `3f4aa40` не менялся)
**Статус:** auth/profile — P0/P1 закрыты и задеплоены; jobs/applications — P0/P1/P2 закрыты и задеплоены; открытых UX-пунктов нет.
**Production (2026-11-03):** `477b22e` (J155–J162: MAX bot, chat search/mute, UTM/retention, anti-spam/moderation, RU/EN i18n, полная локализация кабинета, карта /jobs, репутация v2); ранее — `e98ba24` (J060–J063), auth P001–P114, J029–J058. `/health` 200, Status RUNNING; миграции 72/72.
**Исторический срез аудита (все пункты закрыты):** P0-01…P0-04 (P001–P004);
P1-01/02/06 — P101/P102/P106; P1-03/04/11 — P103/P104; P1-07/08/14 — P107/P108/P114;
BUILD-01 — B001; TASKS-01 — T001; P1-12 — P112; P1-10 ORM — P110; P1-05 — P105.
P1-13 + DB-default P1-10: dev и production — **65/65**, `email_verified default=false`,
gate OK; процедура — [MIGRATION_LEDGER.md](MIGRATION_LEDGER.md).

**Jobs/applications:** P0/P1/P2 закрыты контрактами J001–J058
(открытых пунктов нет; P2-04/P2-07/P2-09 — осознанные решения, P2-12 карта n/a) —
см. [JOBS_RESULTS.md](JOBS_RESULTS.md), [AUDIT_JOBS_APPLICATIONS.md](AUDIT_JOBS_APPLICATIONS.md),
[DISCREPANCIES_JOBS.md](DISCREPANCIES_JOBS.md),
[ROUTES_MATRIX_JOBS.md](ROUTES_MATRIX_JOBS.md),
[UI_INVENTORY_JOBS.md](UI_INVENTORY_JOBS.md). Полный `core` — 595 OK.

**Следующая область:** открытых пунктов паритета auth/profile и jobs/applications нет;
дальше — только продуктовые улучшения из [DESIGN_REVIEW_2026-11.md](../DESIGN_REVIEW_2026-11.md).

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
| [REMAINING_UX.md](REMAINING_UX.md) | закрытые UX-пункты; открытых нет |
| [GEO_UX_PRIVACY.md](GEO_UX_PRIVACY.md) | логика карт/геолокации и меры 152-ФЗ |
| [../DESIGN_REVIEW_2026-11.md](../DESIGN_REVIEW_2026-11.md) | UX/UI-оценка и roadmap |

## Главное (кратко, исторический аудит — всё закрыто)

- **4 P0:** капча (имя поля `smart-token` vs `smart_token`) ломала регистрацию/сброс;
  документы верификации были доступны любому авторизованному; публичный профиль отдавал `contact`;
  в редактировании профиля собирался `religion` (спецкатегория ПДн) — закрыто P001–P004.
- **14 P1:** упрощённая регистрация (ИНН/самозанятость/контакт/портфолио/опыт/оплата/навыки),
  валидация ИНН/контакта, per-IP rate-limit и Redis-cooldown, синхронная почта, инвалидация
  сессий, PDF верификации, `email_verified` fail-open, RLS, ledger, удаление файлов ПДн —
  закрыто P101–P114 и L001.
- **18 P2:** UX-упрощения, URL `/profile` → `/workers`, legacy templates, CSRF 403,
  `|safe` на юридических страницах — закрыто или помечено осознанным решением.

## Что дальше

1. Утвердить severity/приоритеты и решение по 152-ФЗ (P0-02/03/04 — блокеры).
2. Сделать контракты на P0 (по одному на расхождение), затем P1.
3. Runtime contract-проверки: капча с валидным токеном, verification-doc owner/other/admin,
   публичный профиль без ПДн, login rate-limit, инвалидация сессий, e2e кликабельных элементов.
4. После стабилизации — docs-актуализация (отдельные контракты) и повторный parity-прогон.
