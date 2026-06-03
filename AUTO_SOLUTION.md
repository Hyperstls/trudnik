# Финальное решение проблемы с RLS и обновление роли

**Дата:** 2026-06-03

## Проблема
Пользователь `test_employer_final@test.com` имеет роль `worker` вместо `employer`.
RLS блокирует обновление роли через анонимный ключ.
SERVICE_KEY не настроен в конфигурации.

## Решение

### Шаг 1: Получить SERVICE_KEY из Supabase Dashboard

1. Перейдите в [Supabase Dashboard](https://supabase.com/dashboard/project/***REMOVED***/settings/api)
2. Найдите **service_role key** (начинается с `eyJ...`)
3. Скопируйте ключ

### Шаг 2: Добавить SERVICE_KEY в .env файл

Добавьте строку в `.env` файл (в папке проекта `C:/Users/s.prokopenko/PycharmProjects/trudnik/`):

```
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Где `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` - это ваш service_role key.

**ИЛИ** добавьте на PythonAnywhere в `.env` файл в папке `~/mysite/`

### Шаг 3: Выполнить скрипт автоматического решения

После добавления SERVICE_KEY выполните:

```bash
python ultimate_auto_agent.py
```

Этот скрипт автоматически:
1. Проверит конфигурацию
2. Проверит текущую роль
3. Отключит RLS для таблицы profiles
4. Обновит роль на 'employer'
5. Проверит результат
6. Протестирует вход

### Альтернативный способ: Вручную через Supabase Dashboard

Если не хотите использовать SERVICE_KEY:

1. Откройте [Supabase Dashboard](https://supabase.com/dashboard/project/***REMOVED***/table-editor)
2. Найдите таблицу **profiles**
3. Нажмите на три точки (...) -> **Table Settings**
4. Перейдите на вкладку **Row Level Security (RLS)**
5. **Отключите** **Row Level Security**
6. Сохраните изменения
7. Найдите пользователя `c6291021-7741-4a10-b68c-b1c7ec002442`
8. Нажмите на три точки -> **Edit Row**
9. Измените `role` на `employer`
10. Сохраните изменения

### Шаг 4: Проверка результата

После выполнения любого из способов:

```bash
python ultimate_auto_agent.py
```

Ожидаемый результат: редирект на `/my-jobs` после входа.

## Созданные файлы

| Файл | Назначение |
|------|------------|
| `ultimate_auto_agent.py` | Полный автоматический агент для решения проблемы |
| `auto_fix_agent.py` | Агент для проверки и исправления |
| `full_auto_agent.py` | Агент для полного тестирования |
| `super_agent.py` | Простой агент с базовыми командами |
| `disable_rls_agent.py` | Агент для отключения RLS |
| `check_pa_service_key.py` | Проверка SERVICE_KEY из PythonAnywhere |

## Команды для тестирования

```bash
# Полное решение проблемы
python ultimate_auto_agent.py

# Проверка роли
python ultimate_auto_agent.py check_role

# Получение SERVICE_KEY из PythonAnywhere
python ultimate_auto_agent.py get_key

# Тест входа
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"
```

## Статус

- [x] Анализ проблемы
- [x] Создание агентов для автоматизации
- [x] Проверка текущей роли (worker)
- [ ] Получение SERVICE_KEY (ожидание ввода)
- [ ] Отключение RLS (после получения SERVICE_KEY)
- [ ] Обновление роли (после отключения RLS)
- [ ] Тестирование (после обновления роли)

## Что нужно от пользователя

Для завершения решения проблемы необходимо:

1. **Предоставить SERVICE_KEY** из Supabase Dashboard
   - Или добавить его в `.env` файл
   - Или ввести при запросе скриптом

2. **Подтвердить выполнение шагов**
   - Скрипт автоматически выполнит остальные действия

## Рекомендации

1. После тестирования **включите RLS обратно** для безопасности
2. Для продакшена настройте SERVICE_KEY в `.env` файле на PythonAnywhere
3. Используйте `auto_fix_agent.py` для регулярной проверки системы
