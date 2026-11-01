# Индекс документации «Трудник»

**Дата:** 2026-11-01
**Текущий стек:** Django 5.2, Python 3.12, PostgreSQL/PostGIS, Celery/Redis, Channels, Tailwind, Amvera.
**Прод:** трудник.рф; полный `core` — 429 OK, `pre_deploy_check` — 7/7.

## 1. Актуальные документы (источник истины)

| Документ | Назначение |
|---|---|
| [../README.md](../README.md) | стек, структура, быстрый старт, проверки, деплой |
| [../AGENTS.md](../AGENTS.md) | правила для AI-агентов: мультирольность, проверки, секреты |
| [AGENT_PIPELINE.md](AGENT_PIPELINE.md) | контракты, dispatch, verify/review, лимиты |
| [parity/README.md](parity/README.md) | статус паритета Flask→Django, production-коммиты |
| [parity/JOBS_RESULTS.md](parity/JOBS_RESULTS.md) | J001–J058: что сделано, проверки, остаток |
| [parity/DISCREPANCIES_JOBS.md](parity/DISCREPANCIES_JOBS.md) | реестр расхождений jobs/applications |
| [parity/REMAINING_UX.md](parity/REMAINING_UX.md) | закрытые UX-пункты, открытых нет |
| [parity/GEO_UX_PRIVACY.md](parity/GEO_UX_PRIVACY.md) | карты, геолокация, меры 152-ФЗ |
| [parity/152FZ_DATA_FLOWS.md](parity/152FZ_DATA_FLOWS.md) | потоки ПДн и внешние сервисы |
| [parity/MIGRATION_LEDGER.md](parity/MIGRATION_LEDGER.md) | ledger 65/65, reconcile/apply |
| [DESIGN_REVIEW_2026-11.md](DESIGN_REVIEW_2026-11.md) | UX/UI-оценка, сильные/слабые места, roadmap |
| [UX_ROADMAP_2026Q4.md](UX_ROADMAP_2026Q4.md) | приоритеты: черновик/степпер, дизайн-система, сохранённые поиски, CWV/axe |
| [APP_RELEASE.md](APP_RELEASE.md) | APK/TWA: сборка, подпись, assetlinks, страница установки |
| [rkn_notification_fill.md](rkn_notification_fill.md) | уведомление Роскомнадзора (152-ФЗ) |
| [SECRETS_ROTATION_STATUS.md](SECRETS_ROTATION_STATUS.md) | статус утёкших в историю секретов |

## 2. Parity-артефакты (исторические срезы аудита)

Эти файлы фиксируют момент аудита; итоговые статусы — в `parity/README.md` и
`parity/JOBS_RESULTS.md`:

- [parity/AUDIT_AUTH_PROFILE.md](parity/AUDIT_AUTH_PROFILE.md) — аудит auth/profile.
- [parity/P0_RESULTS.md](parity/P0_RESULTS.md), [parity/P1_RESULTS.md](parity/P1_RESULTS.md) — P001–P114.
- [parity/AUDIT_JOBS_APPLICATIONS.md](parity/AUDIT_JOBS_APPLICATIONS.md) — первичный аудит jobs.
- [parity/ROUTES_MATRIX.md](parity/ROUTES_MATRIX.md), [parity/UI_INVENTORY.md](parity/UI_INVENTORY.md) — auth/profile.
- [parity/ROUTES_MATRIX_JOBS.md](parity/ROUTES_MATRIX_JOBS.md), [parity/UI_INVENTORY_JOBS.md](parity/UI_INVENTORY_JOBS.md) — jobs.
- [parity/DISCREPANCIES.md](parity/DISCREPANCIES.md) — исходный реестр auth/profile.
- [parity/CONTRACT_CHECKS.md](parity/CONTRACT_CHECKS.md) — проверки RPC/RLS на момент аудита.

## 3. Legacy Flask (историческое, НЕ описывает текущий прод)

Эти документы писались для Flask-приложения (`app/`) и оставлены как эталон/история.
Не используйте их как инструкцию по текущему Django-коду:

- [ARCHITECTURE.md](ARCHITECTURE.md) — архитектура Flask-монолита.
- [BUSINESS_LOGIC.md](BUSINESS_LOGIC.md) — бизнес-логика Flask (модель данных и правила
  частично актуальны, пути `app/` — нет).
- [API_REFERENCE.md](API_REFERENCE.md), [API_ENDPOINTS.md](API_ENDPOINTS.md) — REST/API Flask.
- [FRONTEND.md](FRONTEND.md) — страницы/JS Flask.
- [BUTTON_REGISTRY.md](BUTTON_REGISTRY.md), [UI_INVENTORY*.md](parity/UI_INVENTORY.md) — старый UI.
- [E2E_SCENARIOS.md](E2E_SCENARIOS.md), [QA_TEST_CASES.md](QA_TEST_CASES.md),
  [TEST_COVERAGE_MAP.md](TEST_COVERAGE_MAP.md) — pytest/Flask-сценарии.
- [A11Y_AUDIT.md](A11Y_AUDIT.md), [SECURITY.md](SECURITY.md), [DEAD_CODE_AUDIT.md](DEAD_CODE_AUDIT.md) —
  аудиты Flask-эпохи (часть выводов перенесена, но файлы устарели).
- [architect_audit_2026-09.md](architect_audit_2026-09.md),
  [architect_audit_prompt_v2.md](architect_audit_prompt_v2.md),
  [django_migration_prompt.md](django_migration_prompt.md) — история миграции.
- [Kimi3 design_audit_2026-08-14.md](Kimi3%20design_audit_2026-08-14.md),
  [Front promt kimi3 by design_audit_2026-08-14.md](Front%20promt%20kimi3%20by%20design_audit_2026-08-14.md) —
  ранний дизайн-аудит.
- [GITHUB_SECRETS_SETUP.md](GITHUB_SECRETS_SETUP.md) — настройка GHA (если CI используется).

## 4. Где что искать

- **Бизнес-правила:** `AGENTS.md`, `docs/parity/JOBS_RESULTS.md`, код `djadmin/core`.
- **Маршруты:** `djadmin/core/urls.py` (актуальнее любой матрицы).
- **Шаблоны:** только `djadmin/core/templates/core/`; корневые `templates/` — legacy.
- **Тесты:** `djadmin/core/tests/`; запуск — `manage.py test core --keepdb`.
- **Контракты:** `context/agent-pipeline/tasks/` и `state.json`.
- **Деплой:** `README.md` + память Amvera/MCP; креды только env.

## 5. Правило актуализации

При изменении маршрута/фичи обновляйте:
1. `docs/parity/JOBS_RESULTS.md` или соответствующий results-файл.
2. `docs/parity/README.md` (статус/коммит).
3. `docs/parity/REMAINING_UX.md` (если пункт закрыт/добавлен).
4. `README.md` (стек/команды/статус тестов).
Legacy-документы не переписываются под Django — они помечены как архив.
