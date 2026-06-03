# Инструкция по отключению RLS для таблицы profiles

## Проблема
RLS (Row Level Security) в Supabase блокирует обновление роли пользователя через анонимный ключ.

## Решение 1: Отключить RLS (рекомендуется для тестирования)

1. Перейдите в Supabase Dashboard: https://supabase.com/dashboard
2. Выберите ваш проект: `***REMOVED***`
3. В левом меню выберите **Table Editor**
4. Найдите таблицу **profiles**
5. Нажмите на три точки (...) рядом с таблицей и выберите **Table Settings**
6. Перейдите на вкладку **Row Level Security (RLS)**
7. Отключите **Row Level Security** для таблицы profiles

ИЛИ:

1. В Table Editor найдите таблицу **profiles**
2. Нажмите на **RLS** в левом меню
3. Нажмите **New Policy**
4. Выберите шаблон: **"All CRUD operations for all users"**
5. Настройки:
   - Name: `Allow all operations`
   - Target: `All operations`
   - Role: `authenticated`
   - USING: `true`
   - WITH CHECK: `true`
6. Нажмите **Save**

## Решение 2: Использовать SERVICE_KEY (рекомендуется для продакшена)

1. Перейдите в Supabase Dashboard -> Settings -> API
2. Скопируйте **service_role key** (начинается с `eyJ...`)
3. Добавьте его в `.env` файл как:
   ```
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
   ```
4. Перезагрузите приложение
5. Теперь можно обновлять роли через SERVICE_KEY

## Проверка

После отключения RLS или добавления SERVICE_KEY запустите:

```bash
python update_role_direct.py
```

Или протестируйте вход через браузерный агент:

```bash
python my_browser_agent.py "Войди как test_employer_final@test.com с паролем 123456 и проверь, что ты попал на страницу my-jobs"
```
