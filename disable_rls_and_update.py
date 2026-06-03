"""
Скрипт для отключения RLS и обновления роли через PythonAnywhere
"""

import requests
import json

SUPABASE_URL = "https://***REMOVED***.supabase.co"

# Попытка 1: Использовать SERVICE_KEY (если есть на PythonAnywhere)
SERVICE_KEY = ""

# Получаем SERVICE_KEY из переменной окружения
import os
if not SERVICE_KEY:
    SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

print("=== Отключение RLS и обновление роли ===")
print(f"SERVICE_KEY: {SERVICE_KEY[:20] if SERVICE_KEY else 'NOT SET'}...")

if not SERVICE_KEY:
    print("\nSERVICE_KEY не найден!")
    print("Пожалуйста, добавьте его в .env файл на PythonAnywhere:")
    print("1. Перейдите в Supabase Dashboard -> Settings -> API")
    print("2. Скопируйте service_role key")
    print("3. Добавьте в .env файл на PythonAnywhere как SUPABASE_SERVICE_ROLE_KEY")
    print("4. Перезапустите приложение")
    exit(1)

# Попытка 2: Отключить RLS
print("\n=== Отключение RLS ===")
sql_url = f"{SUPABASE_URL}/rest/v1/rpc"

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

sql_query = {
    "sql": "ALTER TABLE profiles DISABLE ROW LEVEL SECURITY"
}

try:
    resp = requests.post(sql_url, json=sql_query, headers=headers, timeout=10)
    print(f"Отключение RLS Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("SUCCESS: RLS отключен!")
    else:
        print(f"ERROR: Не удалось отключить RLS (код {resp.status_code})")
        
except Exception as e:
    print(f"Ошибка: {e}")

# Попытка 3: Обновить роль
user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
update_data = {
    "role": "employer",
    "full_name": "Тестовый Работодатель"
}

print("\n=== Обновление роли ===")
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"

try:
    resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("SUCCESS: Роль обновлена!")
    else:
        print(f"ERROR: Не удалось обновить роль (код {resp.status_code})")
        
except Exception as e:
    print(f"Ошибка: {e}")

# Проверка
print("\n=== Проверка результата ===")
check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
resp_check = requests.get(check_url, headers={'apikey': SERVICE_KEY}, timeout=10)

if resp_check.status_code == 200:
    data = resp_check.json()
    if data:
        user = data[0]
        print(f"User ID: {user.get('id')}")
        print(f"Role: {user.get('role')}")
        print(f"Full Name: {user.get('full_name')}")
        
        if user.get('role') == 'employer':
            print("\nSUCCESS: Роль успешно обновлена на 'employer'!")
        else:
            print(f"\nERROR: Роль остается '{user.get('role')}', ожидался 'employer'")
    else:
        print("Пользователь не найден")
else:
    print(f"Ошибка проверки: {resp_check.status_code}")
