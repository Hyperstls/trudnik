"""
Список инструкций для решения проблемы с ролями

## Проблема
Пользователь test_employer_final@test.com зарегистрирован, но имеет роль "worker" вместо "employer".

## Корневая причина
RLS (Row Level Security) в Supabase блокирует обновление роли через анонимный ключ.
SERVICE_KEY не настроен в config.py.

## Решение 1: Отключить RLS (быстрое решение для тестирования)

### В Supabase Dashboard:
1. Перейдите в https://supabase.com/dashboard/project/***REMOVED***/table-editor
2. Найдите таблицу "profiles"
3. Нажмите на три точки (...) -> "Table Settings"
4. Перейдите на вкладку "Row Level Security (RLS)"
5. Отключите "Row Level Security"

### Проверка:
Запустите:
```
python final_update_role.py
```

### Тест входа:
```
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"
```

## Решение 2: Создать политику RLS (более безопасно)

### В Supabase Dashboard:
1. Table Editor -> profiles -> RLS
2. Нажмите "New Policy"
3. Настройки:
   - Name: "Allow users to update their role"
   - Target: "UPDATE"
   - Role: "authenticated"
   - USING: "auth.uid() = id"
   - WITH CHECK: "auth.uid() = id"
4. Нажмите "Save"

## Решение 3: Добавить SERVICE_KEY (рекомендуется для продакшена)

### 1. Получить SERVICE_KEY:
- Supabase Dashboard -> Settings -> API
- Скопировать service_role key

### 2. Добавить в .env файл:
```
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIs...
```

### 3. Обновить config.py (если нужно):
```python
class Config:
    # ... другие настройки ...
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
```

### 4. Запустить скрипт:
```
python final_update_role.py
```

## Проверка результата

После выполнения любого из решений:

1. Проверить профиль пользователя:
```
python test_profile_api.py
```

2. Протестировать вход:
```
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"
```

3. Проверить создание задания:
```
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и создай новое задание с названием 'Тестовое задание'"
```

## Дополнительные команды для тестирования

```
# Просмотр всех профилей
python test_profile_api.py

# Регистрация нового работодателя
python my_browser_agent.py "Зарегистрируй нового работодателя с именем Тестовый, email employer_test@test.com, пароль 123456, город Москва"

# Просмотр заданий работодателя
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и покажи мои задания"

# Создание отклика (для работника)
python my_browser_agent.py "Войди как test_worker_2026@test.com с паролем 123456 и откликнись на первое задание"
```

## Скрипты для отладки

- `test_profile_api.py` - проверка профилей
- `test_auth.py` - проверка авторизации
- `test_register_employer.py` - регистрация работодателя
- `update_profile_role.py` - обновление роли (без SERVICE_KEY)
- `final_update_role.py` - обновление роли (с SERVICE_KEY)
- `disable_rls.py` - отключение RLS (с SERVICE_KEY)
- `create_rls_policy.py` - создание политики RLS
- `test_rls_bypass.py` - тест обхода RLS

## Ожидаемые результаты

После успешного обновления роли:

1. Профиль пользователя должен иметь `"role": "employer"`
2. При входе в аккаунт пользователь должен попасть на `/my-jobs`
3. Пользователь должен видеть кнопку "Создать задание"
4. Пользователь должен видеть список откликов в `/my-applications`
