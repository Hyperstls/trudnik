# Руководство по тестированию Flask-приложения "Трудник" на PythonAnywhere

## Текущая ситуация

Пользователь `test_employer_final@test.com` зарегистрирован, но имеет роль `worker` вместо `employer`.

**Причина**: RLS (Row Level Security) в Supabase блокирует обновление роли через анонимный ключ.

## Решение проблемы

### Вариант 1: Отключить RLS через Supabase Dashboard (БЫСТРЕЙШИЙ)

1. Перейдите в [Supabase Dashboard](https://supabase.com/dashboard/project/***REMOVED***/table-editor)
2. Найдите таблицу **profiles**
3. Нажмите на три точки (...) -> **Table Settings**
4. Перейдите на вкладку **Row Level Security (RLS)**
5. Отключите **Row Level Security**
6. **ВАЖНО**: Не забудьте включить обратно после тестирования!

### Вариант 2: Использовать SERVICE_KEY (БЕЗОПАСНЫЙ)

1. Получите SERVICE_KEY из Supabase Dashboard:
   - Settings -> API -> service_role key
2. Добавьте его в `.env` файл на PythonAnywhere:
   ```
   SUPABASE_SERVICE_ROLE_KEY=ваш_service_role_key_здесь
   ```
3. Перезапустите приложение на PythonAnywhere
4. Выполните скрипт `solution_rls.py` локально или на PythonAnywhere

## Тестирование после исправления роли

### 1. Проверка через my_browser_agent.py

```bash
# Войти как работодатель и проверить страницу my-jobs
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"

# Проверить доступ к созданию задания
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и покажи кнопку создания задания"

# Создать новое задание
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и создай новое задание с названием 'Уборка храма', дата 2026-06-10, оплата 3000"
```

### 2. Проверка через curl

```bash
# Войти
curl -X POST https://hyperstls.pythonanywhere.com/login \
  -d "email=test_employer_final@test.com" \
  -d "password=123456" \
  -c /tmp/cookies.txt

# Проверить роль
curl -b /tmp/cookies.txt https://hyperstls.pythonanywhere.com/profile

# Доступ к my-jobs (должен быть 200, а не 302 редирект на login)
curl -b /tmp/cookies.txt https://hyperstls.pythonanywhere.com/my-jobs
```

### 3. Проверка через test_profile_api.py

```bash
python test_profile_api.py
```

Ожидаемый результат: `role: employer`

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

## Статус тестирования

- [ ] RLS отключен / SERVICE_KEY настроен
- [ ] Роль пользователя обновлена на "employer"
- [ ] Вход работодателя работает
- [ ] Страница my-jobs доступна
- [ ] Создание задания работает
- [ ] Отклики работают
- [ ] Управление откликами работает

## Файлы для отладки

- `my_browser_agent.py` - браузерный агент для тестирования
- `test_profile_api.py` - проверка профилей
- `test_auth.py` - проверка авторизации
- `test_register_employer.py` - регистрация работодателей
- `solution_rls.py` - обновление роли через REST API
- `update_role_via_flask.py` - обновление через Flask API
- `disable_rls.py` - отключение RLS через SQL
