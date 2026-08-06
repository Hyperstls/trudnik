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

3. Мок PostgREST: app/testing/mock_postgrest.py. В тестах _is_mock_enabled()=True → запросы идут в in-memory БД, реальный HTTP/PostgreSQL не нужен.
   conftest.py: stateful redis-mock (get/set/setex/delete/exists), SecureCookieSessionInterface override для auth-сессий, smart postgrest-mock (роль из сессии, B5 existence), auto-skip integration-тестов (AMVERA_RUN_INTEGRATION=1 для запуска).

4. Линтеры/typecheck: в репо НЕТ отдельных команд lint/typecheck (нет ruff/mypy). Верификация — через pytest.
   detect-secrets: pre-commit хук. При добавлении тестовых паролей используй 'Aa1!aaaa' (низкая энтропия, НЕ флагируется). НЕ используй 'StrongP@ss1' (GitGuardian флагает).
   После изменений, затрагивающих секреты: `.venv\Scripts\python.exe -m detect_secrets scan --baseline .secrets.baseline`

5. Локальный прогон сервисов (docker-compose):
   docker-compose up -d redis db postgrest
   docker-compose up web                 # Flask dev-сервер, только HTTP
   WS локально: trudnik-websocket контейнер (uvicorn websocket_server.main:app --port 8001)
   ⚠️ Redis имеет пароль: trudnik-local-dev (docker-compose --requirepass, .env REDIS_URL)

6. Перед деплоем: прогони pytest (минимум tests), убедись в отсутствии регрессий. Сам деплой — через 06_amvera_deploy.md.
7. CI: GitHub Actions `.github/workflows/test.yml` прогоняет pytest, `build-apk.yml` собирает APK. Автодеплой через CI НЕ настроен — деплой ручной (06_amvera_deploy.md).
