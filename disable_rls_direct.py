"""
Скрипт для отключения RLS и обновления роли
"""

import requests
import json
from dotenv import load_dotenv
import os

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://***REMOVED***.supabase.co")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if not SERVICE_KEY:
    print("SERVICE_KEY не найден!")
    exit(1)

print(f"SERVICE_KEY: {SERVICE_KEY[:20]}...")

# Отключение RLS
print("\n=== Отключение RLS ===")
sql_url = f"{SUPABASE_URL}/rest/v1/rpc"
headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

sql_data = {"sql": "ALTER TABLE profiles DISABLE ROW LEVEL SECURITY"}

try:
    resp = requests.post(sql_url, json=sql_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("SUCCESS: RLS отключен!")
    else:
        print(f"ERROR: {resp.status_code}")
        print("Попробуем через REST API напрямую...")
        
        # Альтернативный способ - через REST API
        headers_rest = {
            'apikey': SERVICE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        
        # Попытка через PGRest RPC
        rpc_url = f"{SUPABASE_URL}/rpc"
        resp = requests.post(rpc_url, json=sql_data, headers=headers_rest, timeout=10)
        print(f"RPC Status: {resp.status_code}")
        print(f"RPC Response: {resp.text}")
        
except Exception as e:
    print(f"ERROR: {e}")

# Обновление роли
print("\n=== Обновление роли ===")
update_data = {"role": "employer", "full_name": "Тестовый Работодатель"}
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.c6291021-7741-4a10-b68c-b1c7ec002442"

try:
    resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("SUCCESS: Роль обновлена!")
    else:
        print(f"ERROR: {resp.status_code}")
        
except Exception as e:
    print(f"ERROR: {e}")

# Проверка
print("\n=== Проверка результата ===")
check_headers = {'apikey': SERVICE_KEY, 'Authorization': f'Bearer {SERVICE_KEY}'}
check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.c6291021-7741-4a10-b68c-b1c7ec002442&select=*"

try:
    resp = requests.get(check_url, headers=check_headers, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if data:
            user = data[0]
            print(f"User ID: {user.get('id')}")
            print(f"Role: {user.get('role')}")
            print(f"Full Name: {user.get('full_name')}")
            
            if user.get('role') == 'employer':
                print("\nSUCCESS: Роль успешно обновлена на 'employer'!")
            else:
                print(f"\nERROR: Роль остается '{user.get('role')}'")
        else:
            print("Пользователь не найден")
    else:
        print(f"ERROR: {resp.status_code}")
except Exception as e:
    print(f"ERROR: {e}")
