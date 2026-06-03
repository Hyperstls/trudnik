"""
Скрипт для создания политики RLS, разрешающей обновление роли

Политика: "Разрешить всем пользователям обновлять свою роль"
"""

import requests

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_KEY = "***REMOVED***"

# Политика RLS для таблицы profiles
# Позволяет всем аутентифицированным пользователям обновлять свою роль

policy_sql = """
{
    "name": "Allow users to update their own role",
    "table": "profiles",
    "command": "UPDATE",
    "roles": ["authenticated"],
    "using": "auth.uid() = id",
    "with_check": "auth.uid() = id"
}
"""

# Для создания политики нужен SERVICE_KEY
# Поэтому используем REST API напрямую

print("=== Создание политики RLS для обновления роли ===")

# Создаем политику через SQL REST API
# Но для этого нужен SERVICE_KEY...

# Альтернатива: Отключить RLS для таблицы profiles
# SQL: ALTER TABLE profiles DISABLE ROW LEVEL SECURITY

print("\nИнструкция по созданию политики RLS вручную:")

print("""
1. Перейдите в Supabase Dashboard -> Table Editor -> profiles
2. Нажмите на "RLS" в левом меню
3. Нажмите "New Policy"
4. Настройки:
   - Name: "Allow users to update their role"
   - Target: "UPDATE"
   - Role: "authenticated"
   - USING: "auth.uid() = id"
   - WITH CHECK: "auth.uid() = id"
5. Нажмите "Save"

После этого можно будет обновлять роль через анонимный ключ.

АЛЬТЕРНАТИВА (для быстрого теста):
Отключите RLS для таблицы profiles:
1. Table Editor -> profiles -> Table Settings -> Row Level Security
2. Отключите "Row Level Security"
""")
