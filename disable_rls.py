"""
Скрипт для отключения RLS для таблицы profiles (только для тестирования!)

Внимание: Отключает RLS для таблицы profiles, что делает её доступной для всех!
Используйте только в тестовой среде!
"""

import requests
import json

SUPABASE_URL = "https://***REMOVED***.supabase.co"

# Для выполнения этого запроса нужен SERVICE_KEY
# Получить его можно в Supabase Dashboard -> Settings -> API -> service_role key

SERVICE_KEY = ""

if not SERVICE_KEY:
    print("SERVICE_KEY не задан!")
    print("Пожалуйста, укажите SERVICE_KEY в скрипте или в .env файле")
    print("1. Перейдите в Supabase Dashboard -> Settings -> API")
    print("2. Скопируйте service_role key (начинается с eyJ...)")
    print("3. Добавьте его в .env файл как SUPABASE_SERVICE_ROLE_KEY")
    print("4. Или укажите прямо в скрипте (не рекомендуется)")
    exit(1)

# Выполнение SQL через REST API
sql_url = f"{SUPABASE_URL}/rest/v1/rpc"

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

# Выключаем RLS для таблицы profiles
# Это небезопасно для продакшена!
sql_query = """
{
    "sql": "ALTER TABLE profiles DISABLE ROW LEVEL SECURITY"
}
"""

print("=== Выполнение SQL через RPC ===")
print(f"URL: {sql_url}")
print(f"Headers: {headers}")
print(f"Query: {sql_query}")

try:
    resp = requests.post(sql_url, data=sql_query, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("\nSUCCESS: RLS отключен для таблицы profiles!")
        print("\nТеперь можно обновлять роль через анонимный ключ:")
        print("  PATCH /rest/v1/profiles?id=eq.{user_id}")
        print("  Body: {\"role\": \"employer\"}")
    else:
        print(f"\nERROR: Не удалось отключить RLS")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"Ошибка: {e}")
