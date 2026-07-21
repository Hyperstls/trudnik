@rule code test
Как проверять изменения в Trudnik перед коммитом/деплоем.

1. Установка dev-зависимостей:
   pip install -r requirements-dev.txt
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

3. Мок PostgREST: app/testing/mock_postgrest.py. В тестах _is_mock_enabled()=True → запросы идут в in-memory БД, реальный HTTP/PostgreSQL не нужен. Фикстуры — tests/conftest.py и tests_e2e/conftest.py.

4. Линтеры/typecheck: в репо НЕТ отдельных команд lint/typecheck (нет ruff/mypy). Верификация — через pytest. Если вводишь инструмент — пропиши команду в AGENTS.md.

5. Локальный прогон сервисов (docker-compose):
   docker-compose up -d redis db postgrest
   docker-compose up web                 # Flask dev-сервер, только HTTP
   WS локально: uvicorn asgi:application --port 8001

6. Перед деплоем: прогони pytest (минимум tests), убедись в отсутствии регрессий. Сам деплой — через 06_amvera_deploy.md.
7. CI: GitHub Actions `.github/workflows/test.yml` прогоняет pytest, `build-apk.yml` собирает APK. Автодеплой через CI НЕ настроен — деплой ручной (06_amvera_deploy.md).
