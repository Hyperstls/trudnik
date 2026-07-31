# tests/manual — standalone CLI/браузерные скрипты (НЕ собираются pytest)

Перенесены из tests/ при реструктуризации (Фаза 1a). Это standalone-скрипты,
запускаемые вручную (python tests/manual/<name>.py), требующие живого
окружения (запущенный app:8000, selenium-драйвер, тестовые креды в env).
Они НЕ являются pytest-тестами и исключены из 	estpaths, чтобы не ломать
pytest tests коллекцию (часть из них вызывает sys.exit при импорте).

## Состав
- test_job_lifecycle.py      — lifecycle (нужны TRUDNIK_*_EMAIL/PASS env + app)
- test_login_browser.py      — selenium: логин
- test_favorites_browser.py  — selenium: избранное
- test_selenium_browser.py   — selenium: общий прогон
- test_selenium_v2.py        — selenium v2
- test_avatar_upload.py      — selenium: загрузка аватара
- test_register_manual.py    — ручная регистрация тестовых юзеров

## Запуск
Сначала поднять стек (docker-compose) + app, затем:
    python tests/manual/test_login_browser.py
