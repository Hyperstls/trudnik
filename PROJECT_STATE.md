# Текущее состояние проекта "Трудник"

## Дата отчета: 2026-06-03

## Проблемы

### 1. Проблема с ролями
Пользователь `test_employer_final@test.com` зарегистрирован, но имеет роль `worker` вместо `employer`.

### 2. Причина
RLS (Row Level Security) в Supabase блокирует обновление роли через анонимный ключ.
SERVICE_KEY не настроен в `.env` файле на PythonAnywhere.

## Решение

### Шаг 1: Отключить RLS для таблицы profiles
1. Перейдите в [Supabase Dashboard](https://supabase.com/dashboard/project/***REMOVED***/table-editor)
2. Найдите таблицу **profiles**
3. Нажмите на три точки (...) -> **Table Settings**
4. Перейдите на вкладку **Row Level Security (RLS)**
5. Отключите **Row Level Security**

### Шаг 2: Обновить роль через REST API
Загрузите скрипт `update_role_quick.py` на PythonAnywhere и выполните:
```bash
python update_role_quick.py
```

ИЛИ выполните через Flask-приложение:
```bash
python remote_update_role.py
```

### Шаг 3: Проверить результат
После обновления проверьте профиль:
```bash
python test_profile_api.py
```

Убедитесь, что роль пользователя `c6291021-7741-4a10-b68c-b1c7ec002442` стала `employer`.

### Шаг 4: Протестировать вход
```bash
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"
```

## Дополнительные скрипты для отладки

- `test_profile_api.py` - проверка профилей
- `test_auth.py` - проверка авторизации
- `update_role_quick.py` - быстрое обновление роли (на PythonAnywhere)
- `remote_update_role.py` - обновление через Flask
- `final_update_role.py` - обновление с SERVICE_KEY (локально)

## Ожидаемые результаты

После успешного обновления роли:

1. **Профиль пользователя** должен иметь `"role": "employer"`
2. **Вход** должен перенаправлять на `/my-jobs`
3. **Страница my-jobs** должна показывать список заданий
4. **Кнопка "Создать задание"** должна быть доступна
5. **Кнопка "Мои отклики"** должна работать

## Команды для тестирования всех функций

```
# 1. Регистрация работника
python my_browser_agent.py "Зарегистрируй нового работника с именем Иван, email worker_ivan@test.com, пароль 123456, город Санкт-Петербург, навыки Python, JavaScript"

# 2. Регистрация работодателя
python my_browser_agent.py "Зарегистрируй нового работодателя с именем Храм, email employer_hram@test.com, пароль 123456, город Москва, религия Православие"

# 3. Вход работника
python my_browser_agent.py "Войди как worker_ivan@test.com с паролем 123456 и покажи список заданий"

# 4. Вход работодателя
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и покажи мои задания"

# 5. Создание задания
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и создай новое задание с названием 'Уборка храма', дата 2026-06-10, оплата 3000"

# 6. Отклик на задание
python my_browser_agent.py "Войди как worker_ivan@test.com с паролем 123456 и откликнись на задание 'Уборка храма'"

# 7. Просмотр откликов
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и покажи мои отклики"

# 8. Принятие работника
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и примени работника worker_ivan@test.com на задание 'Уборка храма'"
```

## Следующие шаги

1. Отключить RLS для таблицы profiles в Supabase Dashboard
2. Выполнить скрипт `update_role_quick.py` на PythonAnywhere
3. Проверить, что роль обновилась на `employer`
4. Протестировать вход через `my_browser_agent.py`
5. Протестировать создание задания
6. Протестировать отклики
7. Заполнить `PLAN_TESTS.md` результатами

## Файлы

- `my_browser_agent.py` - браузерный агент для тестирования
- `app.py` - Flask приложение
- `config.py` - конфигурация
- `test_*.py` - тестовые скрипты
- `update_role_*.py` - скрипты для обновления ролей
