# Руководство по автоматическому тестированию "Трудник"

## Дата отчета: 2026-06-03

## Статус проблемы

**Проблема:** Пользователь `test_employer_final@test.com` имеет роль `worker` вместо `employer`.

**Причина:** SERVICE_KEY не настроен в локальной конфигурации, RLS блокирует обновление роли через анонимный ключ.

## Созданные агенты

### 1. full_auto_agent.py (РЕКОМЕНДУЕТСЯ)
Полный автоматический агент для тестирования.

**Команды:**
- `check_all` - Проверить всё (конфиг, роль, вход)
- `fix_rls` - Инструкции по отключению RLS
- `test_login` - Протестировать вход работодателя
- `fix_role` - Создать скрипт для исправления роли
- `auto_test` - Автоматическое тестирование

**Использование:**
```bash
python full_auto_agent.py auto_test
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
python auto_fix_agent.py full_check
```

### 3. super_agent.py
Простой агент с базовыми командами.

**Команды:**
- `update_role` - Обновить роль пользователя
- `disable_rls` - Инструкции по отключению RLS
- `test_login` - Протестировать вход работодателя
- `full_test` - Полный цикл тестирования

**Использование:**
```bash
python super_agent.py update_role
```

### 4. fix_role_via_service_key.py
Создаётся автоматически через `auto_fix_agent.py create_fix`.

**Назначение:** Обновить роль пользователя через PythonAnywhere с SERVICE_KEY.

**Использование:**
```bash
# Загрузите на PythonAnywhere и выполните
python fix_role_via_service_key.py
```

## Быстрый старт

### Шаг 1: Запуск полного тестирования
```bash
python full_auto_agent.py auto_test
```

Это выполнит:
1. Проверку конфигурации
2. Проверку роли пользователя
3. Тест входа работодателя

**Ожидаемый результат:**
- Роль должна быть `worker` (подтверждено)
- Вход должен редиректить на `/` вместо `/my-jobs`

### Шаг 2: Отключение RLS (если нужно)

```bash
python full_auto_agent.py fix_rls
```

Последуйте инструкциям:
1. Перейдите в Supabase Dashboard
2. Найдите таблицу 'profiles'
3. Три точки -> Table Settings -> Row Level Security -> Отключите
4. Сохраните

**Альтернативно:** Включите RLS обратно после тестирования.

### Шаг 3: Обновление роли

**Вариант A: Через PythonAnywhere (с SERVICE_KEY)**

Загрузите `fix_role_via_service_key.py` на PythonAnywhere и выполните:
```bash
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

**Ожидаемый результат:** Редирект на `/my-jobs` после входа.

### Шаг 5: Полный цикл тестирования

```bash
# Создайте задание
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и создай новое задание с названием 'Уборка храма', дата 2026-06-10, оплата 3000"

# Проверьте отклики
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и покажи мои отклики"
```

## Результаты текущего тестирования

```
=== Шаг 1: Проверка конфигурации ===
[OK] SERVICE_KEY найден в config.py
[WARN] SERVICE_KEY загружается из переменной окружения
   Убедитесь, что SUPABASE_SERVICE_ROLE_KEY задана в .env файле

=== Шаг 2: Проверка роли пользователя ===
[OK] Выполнено (код: 0)
[OUTPUT] Role: worker

=== Шаг 3: Тест входа работодателя ===
[OK] Выполнено (код: 0)
Email: test_employer_final@test.com, Password: 123456
После входа URL: https://hyperstls.pythonanywhere.com/
INFO: Переход на: https://hyperstls.pythonanywhere.com/

=== РЕЗУЛЬТАТ ===
Роль: worker (НЕТ)
Вход: на главную страницу (НЕТ)
```

## Проблемы и решения

### Проблема: SERVICE_KEY не настроен
**Решение:** Добавьте SERVICE_KEY в .env файл на PythonAnywhere.

1. Перейдите в Supabase Dashboard -> Settings -> API
2. Скопируйте **service_role key**
3. Добавьте в .env файл на PythonAnywhere:
   ```
   SUPABASE_SERVICE_ROLE_KEY=ваш_ключ_здесь
   ```
4. Перезапустите приложение

### Проблема: RLS блокирует обновление
**Решение:** Отключите RLS в Supabase Dashboard.

1. Open Supabase Dashboard
2. Table Editor -> profiles -> Table Settings
3. Row Level Security -> Отключите
4. Save

### Проблема: Роль не обновляется
**Решение:** Проверьте:
1. RLS отключен
2. SERVICE_KEY настроен
3. Правильный user_id: `c6291021-7741-4a10-b68c-b1c7ec002442`
4. Запустите `auto_fix_agent.py create_fix` и следуйте инструкциям

## Дополнительные скрипты

- `test_profile_api.py` - Проверка профилей
- `test_auth.py` - Проверка авторизации
- `test_register_employer.py` - Регистрация работодателей
- `solution_rls.py` - Обновление роли через REST API
- `disable_rls.py` - Отключение RLS через SQL

## Контакты

Если возникли проблемы:
1. Проверьте логи в `auto_fix_agent.py`
2. Запустите `full_auto_agent.py auto_test`
3. Проверьте SERVICE_KEY в .env файле на PythonAnywhere
