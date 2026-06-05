# Трудник — платформа для поиска временной подработки

**Дата:** 2026-06-05
**Статус:** ✅ Миграция с PythonAnywhere на Render

---

## 🚀 Деплой на Render

Проект автоматически деплоится на [Render](https://dashboard.render.com) при каждом `git push` в ветку `main`.

### Первичная настройка на Render

1. Создать новый **Web Service** на [dashboard.render.com](https://dashboard.render.com)
2. Подключить GitHub-репозиторий
3. Настроить параметры:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Добавить переменные окружения в разделе **Environment**:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SECRET_KEY`
   - `YANDEX_MAPS_API_KEY`
   - `DEEPSEEK_API_KEY` (опционально)

Либо используйте файл `render.yaml` из корня проекта для конфигурации через **Blueprint** (Infrastructure as Code).

### После деплоя

1. Render автоматически соберёт и запустит приложение
2. Приложение будет доступно по URL вида `https://trudnik.onrender.com`

---

## 📊 Технологический стек

- **Backend**: Python 3.14 + Flask (Application Factory + Blueprints)
- **База данных**: Supabase (PostgreSQL)
- **Фронтенд**: HTML5 + Tailwind CSS (CDN) + Jinja2
- **Хостинг**: Render (автоматический деплой из GitHub)
- **WSGI-сервер**: Gunicorn

---

## 🛠 Локальная разработка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск
python app.py
```

Приложение будет доступно на `http://localhost:5000`.

---

## 📁 Структура проекта

| Директория/Файл | Назначение |
|-----------------|------------|
| `app.py` | Точка входа |
| `app/` | Основной код (Blueprints, утилиты, конфигурация) |
| `templates/` | HTML-шаблоны (Jinja2) |
| `static/` | Статические файлы (CSS, JS, иконки) |
| `migrations/` | SQL-миграции для Supabase |
| `archive/` | Архив старых скриптов и документации |
| `render.yaml` | Конфигурация деплоя на Render |
| `requirements.txt` | Python-зависимости |

---

**Готово к деплою на Render! 🎉**
