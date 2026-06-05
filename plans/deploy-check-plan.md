# План проверки готовности к деплою проекта «Трудник»

## 1. Проверка Git-статуса
- Выполнить `git status` для проверки незавершённых изменений
- Проверить наличие незакоммиченных файлов
- Проверить, есть ли файлы вне `.gitignore`

## 2. Проверка синтаксиса Python
- Выполнить `python -m py_compile app.py` для точки входа
- Выполнить `python -m py_compile app/__init__.py`
- Выполнить `python -m py_compile app/config.py`
- Выполнить `python -m py_compile app/utils.py`
- Выполнить `python -m py_compile app/decorators.py`
- Выполнить `python -m py_compile` для каждого blueprint'а:
  - `app/blueprints/auth.py`
  - `app/blueprints/profile.py`
  - `app/blueprints/jobs.py`
  - `app/blueprints/applications.py`
  - `app/blueprints/shifts.py`
  - `app/blueprints/chat.py`
  - `app/blueprints/favorites.py`
  - `app/blueprints/blacklist.py`
  - `app/blueprints/notifications.py`
  - `app/blueprints/admin.py`
  - `app/blueprints/__init__.py`
- Выполнить `python -m py_compile supabase_agent.py`
- Выполнить `python -m py_compile tests/test_all_functions.py`

## 3. Проверка импортов и сборки
- Попробовать импортировать приложение: `python -c "from app import create_app; print('OK')"`
- Убедиться, что все зависимости установлены: `pip install -r requirements.txt` (или проверка)

## 4. Запуск тестов
- Выполнить `python -m pytest tests/test_all_functions.py -v` (или `python -m unittest tests.test_all_functions -v`)
- Проверить, что все тесты проходят успешно

## 5. Проверка отсутствия `.env` в репозитории
- `.env` должен быть в `.gitignore` — проверить через `git status`

## 6. Принятие решения
- Если все проверки пройдены успешно → деплой разрешён
- Если есть ошибки, незавершённые изменения или проблемы → деплой отменяется с подробным отчётом
