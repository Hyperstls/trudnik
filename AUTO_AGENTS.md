# Автоматические агенты для "Трудник"

## Созданные файлы

### 1. super_agent.py
Простой агент с базовыми командами.

**Команды:**
- `update_role` - Обновить роль пользователя
- `disable_rls` - Инструкции по отключению RLS
- `test_login` - Протестировать вход работодателя
- `full_test` - Полный цикл тестирования

**Использование:**
```bash
python super_agent.py <команда>
```

### 2. auto_fix_agent.py
Расширенный агент для проверки и исправления.

**Команды:**
- `check_config` - Проверить конфигурацию
- `check_role` - Проверить роль пользователя
- `create_fix` - Создать скрипт для исправления роли
- `fix_role` - Попытаться обновить роль автоматически
- `full_check` - Полная проверка системы

**Использование:**
```bash
python auto_fix_agent.py <команда>
```

### 3. full_auto_agent.py
Полный автоматический агент для тестирования.

**Команды:**
- `check_all` - Проверить всё (конфиг, роль, вход)
- `fix_rls` - Инструкции по отключению RLS
- `test_login` - Протестировать вход работодателя
- `fix_role` - Создать скрипт для исправления роли
- `auto_test` - Автоматическое тестирование

**Использование:**
```bash
python full_auto_agent.py <команда>
```

### 4. fix_role_via_service_key.py
Создаётся автоматически через `auto_fix_agent.py create_fix`.

**Назначение:** Обновить роль пользователя через PythonAnywhere с SERVICE_KEY.

**Использование:**
```bash
# Загрузите на PythonAnywhere и выполните
python fix_role_via_service_key.py
```

### 5. my_browser_agent.py (обновлён)
Упрощённый браузерный агент без зависимостей от OpenAI.

**Команды:**
```bash
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"
```

## Быстрый старт

### Шаг 1: Проверка системы
```bash
python full_auto_agent.py auto_test
```

Это выполнит:
1. Проверку конфигурации
2. Проверку роли пользователя
3. Тест входа работодателя

### Шаг 2: Отключение RLS (если нужно)
```bash
python full_auto_agent.py fix_rls
```

Последуйте инструкциям:
1. Перейдите в Supabase Dashboard
2. Найдите таблицу 'profiles'
3. Table Settings -> Row Level Security -> Отключите
4. Сохраните

### Шаг 3: Обновление роли

**Вариант A: Через PythonAnywhere (с SERVICE_KEY)**
```bash
# На PythonAnywhere
python fix_role_via_service_key.py
```

**Вариант B: Вручную через Supabase Dashboard**
1. Open Table Editor -> profiles
2. Найдите пользователя `c6291021-7741-4a10-b68c-b1c7ec002442`
3. Edit Row -> Измените role на 'employer'
4. Save

### Шаг 4: Проверка результата
```bash
python full_auto_agent.py test_login
```

Ожидаемый результат: редирект на `/my-jobs` после входа.

## Полный цикл тестирования

```bash
# 1. Проверка
python full_auto_agent.py auto_test

# 2. Исправление RLS
python full_auto_agent.py fix_rls
# (выполните инструкции вручную)

# 3. Обновление роли (на PythonAnywhere)
python fix_role_via_service_key.py

# 4. Проверка входа
python full_auto_agent.py test_login

# 5. Тест всех функций
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и создай новое задание с названием 'Уборка храма', дата 2026-06-10, оплата 3000"
```

## Проблемы и решения

### Проблема: SERVICE_KEY не настроен
**Решение:** Добавьте SERVICE_KEY в .env файл на PythonAnywhere.

### Проблема: RLS блокирует обновление
**Решение:** Отключите RLS в Supabase Dashboard (см. `fix_rls`).

### Проблема: Роль не обновляется
**Решение:** Проверьте:
1. RLS отключен
2. SERVICE_KEY настроен
3. Правильный user_id
4. Запустите `auto_fix_agent.py create_fix` и следуйте инструкциям

## Файлы для отладки

- `test_profile_api.py` - Проверка профилей
- `test_auth.py` - Проверка авторизации
- `test_register_employer.py` - Регистрация работодателей
- `disable_rls.py` - Отключение RLS через SQL
- `solution_rls.py` - Обновление роли через REST API
