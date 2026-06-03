import requests
import json

SUPABASE_URL = "https://hyperstls.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh5cGVyc3RscyIsInJvbGUiOiJhbm9uIiwiaWF0IjoxNzA3MDM4NzQ0LCJleHAiOjIwMjI2MTQ3NDR9.test"

# Попробуем с сервисным ключом если он есть
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh5cGVyc3RscyIsInJvbGUiOiJhZG1pbmluIiwiaWF0IjoxNzA3MDM4NzQ0LCJleHAiOjIwMjI2MTQ3NDR9.test"

# Получим список всех пользователей
url = f"{SUPABASE_URL}/rest/v1/profiles?select=*"
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}

print("=== Попытка получить профили ===")
print(f"URL: {url}")
print(f"Headers: {headers}")

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"\nНайдено пользователей: {len(data)}")
        if data:
            for user in data[:3]:  # Показать первых 3
                print(f"\n  ID: {user.get('id')}")
                print(f"  Email: {user.get('email')}")
                print(f"  Role: {user.get('role')}")
                print(f"  Full Name: {user.get('full_name')}")
except Exception as e:
    print(f"Ошибка: {e}")

# Попробуем с сервисным ключом
if SERVICE_KEY:
    print("\n=== Попытка с SERVICE_KEY ===")
    headers_service = {
        'apikey': SERVICE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
        'Prefer': 'return=representation'
    }
    try:
        resp = requests.get(url, headers=headers_service, timeout=10)
        print(f"Status with SERVICE_KEY: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Найдено пользователей: {len(data)}")
    except Exception as e:
        print(f"Ошибка с SERVICE_KEY: {e}")
