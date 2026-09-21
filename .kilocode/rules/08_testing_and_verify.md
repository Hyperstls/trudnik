@rule code test
Как проверять изменения в Trudnik перед коммитом/деплоем.

1. Установка dev-зависимостей (venv Python 3.12):
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   playwright install chromium        # для e2e

2. Запуск тестов (pytest.ini: testpaths=tests tests_e2e, asyncio_mode=auto):
   - Всё:                       pytest
   - Только unit:               pytest tests
   - Только e2e (Playwright):   pytest tests_e2e        (маркер e2e)
   - Без медленных:             pytest -m "not slow"
   - Интеграционные:            pytest -m integration
   - Accessibility (axe-core):  pytest -m a11y
   - С покрытием:               pytest --cov            (pytest-cov)
   Маркеры: slow, integration, e2e, a11y.
   ВАЖНО: перед прогоном установи `$env:REDIS_URL='redis://:trudnik-local-dev@localhost:6379/0'`
   (Redis-пароль trudnik-local-dev, см. docker-compose).
   ВАЖНО: при правках templates/ или static/js/ перед коммитом — `npm run build:css`
   (иначе упадут pre_deploy_check [7/7] и CI git diff на tailwind.min.css).

3. Мок PostgREST: app/testing/mock_postgrest.py. АКТИВЕН в suite: гейт `POSTGREST_MOCK_MODE in ('1','true','yes')`
   (conftest выставляет); `_install_auth_mock` вызывается в КОНЦЕ app/utils/__init__ (circular import устранён).
   При mock запросы идут в in-memory БД, реальный HTTP/PostgreSQL не нужен.
   Многие тесты патчат postgrest на уровне blueprint — оба подхода легальны.
   CB-тесты (Circuit Breaker) skipif при активном mock: CircuitBreaker.call обходит CB в mock (by design).
   conftest.py: stateful redis-mock (get/set/setex/delete/exists), SecureCookieSessionInterface override для auth-сессий, smart postgrest-mock (роль из сессии, B5 existence), auto-skip integration-тестов (AMVERA_RUN_INTEGRATION=1 для запуска).
   Примеры актуальных тестов: tests/test_apply_unapply_api.py, test_chat_access.py,
   test_my_applications_skills_filter.py, test_ratings_upsert_per_rated_user.py, test_validators.py;
   e2e — tests_e2e/test_revived_ui.py (модалки rating/invite, apply без reload, profile-menu, чат, delete-account).

4. Линтеры/typecheck: в репо НЕТ отдельных команд lint/typecheck (нет ruff/mypy). Верификация — через pytest.
   detect-secrets: pre-commit хук. При добавлении тестовых паролей используй 'Aa1!aaaa' (низкая энтропия, НЕ флагируется). НЕ используй 'StrongP@ss1' (GitGuardian флагает).
   После изменений, затрагивающих секреты: `.venv\Scripts\python.exe -m detect_secrets scan --baseline .secrets.baseline`

5. Локальный прогон сервисов (docker-compose):
   docker-compose up -d redis db postgrest
   docker-compose up web                 # Flask dev-сервер, только HTTP
   WS локально: trudnik-websocket контейнер (uvicorn websocket_server.main:app --port 8001)
   ⚠️ Redis имеет пароль: trudnik-local-dev (docker-compose --requirepass, .env REDIS_URL)

6. Live-тесты (tests/test_critical_gaps.py, test_backend_gaps.py) и e2e — нужен поднятый web.
   Flask dev-server (bind-mount) может отдавать устаревшие шаблоны → `docker compose restart web` после правок шаблонов.
   Login-хелпер live-тестов шлёт `_csrf_token` и сбрасывает rate-limit ключи (tests.conftest._clear_login_rate_limits).
   Ожидания live: `/login` на блокировку — 200+flash (НЕ 429); `/jobs/<invalid>` → 302+flash «Задание не найдено» (не 404);
   `/api/search/*` НЕ существует (поиск — SSR на /); `/api/religions` 404 by design (спецкатегория ПДн);
   health — `/health` (не /api/health); own id — из `/profile/export-data`.
   e2e-ловушки (Playwright): CSP запрещает wait_for_function/eval → wait_for_selector;
   против optimistic-detach — dispatch_event('click').
   bcrypt `$2b$` (прод PG17) НЕ работает в локальном pgcrypto (PG15 Alpine — только `$2a$`):
   для локальных тестовых паролей — replace префикса.

7. Перед деплоем: прогони pytest (минимум tests), убедись в отсутствии регрессий. Сам деплой — через 06_amvera_deploy.md.
8. CI: GitHub Actions `.github/workflows/test.yml` прогоняет pytest + `npm ci && npm run build:css && git diff --exit-code static/css/tailwind.min.css`, `build-apk.yml` собирает APK. Автодеплой через CI НЕ настроен — деплой ручной (06_amvera_deploy.md).
