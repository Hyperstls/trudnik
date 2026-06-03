import requests
import json

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_KEY = "***REMOVED***"

# Пробуем использовать service_role через REST API напрямую (с опцией header)
# В Supabase есть способ обойти RLS через заголовки

# Вариант 1: Использовать X-Client-Info (не сработает)
# Вариант 2: Отключить RLS для таблицы profiles (для разработки)
# Вариант 3: Создать политику для всех пользователей

print("=== Вариант: Прямой SQL через REST API (через service_role) ===")
print("Для этого нужно использовать service_role ключ в заголовке")

# Попробуем через RPC (remote procedure call)
# Supabase Auth имеет функцию для обновления user_metadata

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

# Пробуем обновить через Auth API (но это только для user_metadata, не для profiles)
auth_update_url = f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}"

# Пробуем использовать service_role через заголовок
# Но у нас нет service_role ключа...

# Решение: Обновить role через profiles API с правильным заголовком
# Нужно отключить RLS для таблицы profiles или использовать service_role

print("\n=== РЕШЕНИЕ 1: Отключить RLS для profiles (тест) ===")
print("В Supabase Dashboard -> Table Editor -> profiles -> RLS")
print("1. Отключить Row Level Security для таблицы profiles")
print("2. Или создать политику: \"Enable all operations for all users\"")
print("   - Template: \"All CRUD operations for all users\"")
print("   - Role: \"authenticated\"")
print("   - USING (true)")
print("   - WITH CHECK (true)")

print("\n=== РЕШЕНИЕ 2: Использовать service_role (рекомендуется) ===")
print("1. Получить service_role ключ из Supabase Dashboard -> Settings -> API")
print("2. Добавить его в .env файл как SUPABASE_SERVICE_ROLE_KEY")
print("3. Использовать для обновления профилей")

print("\n=== РЕШЕНИЕ 3: Через Flask приложение (с SERVICE_KEY в config) ===")
print("Если SERVICE_KEY будет добавлен в config.py, то обновление сработает")

# Попробуем обновить через app.py напрямую
print("\n=== Проверка app.py логики ===")
print("В app.py есть код для обновления роли при регистрации:")
print("  if 'test' in email.lower() and role == 'employer':")
print("      update_data['role'] = 'employer'")
print("  if SERVICE_KEY:")
print("      # обновление через SERVICE_KEY")
print("  else:")
print("      # обновление через supabase_request")

print("\n=== РЕЗЮМЕ ===")
print("Для тестирования нужно:")
print("1. Либо отключить RLS для profiles в Supabase Dashboard")
print("2. Либо добавить SERVICE_KEY в .env и config.py")
print("3. Либо создать политику RLS, разрешающую обновление role")
