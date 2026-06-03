import sys
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://***REMOVED***.supabase.co')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

print("=== Обновление роли пользователя ===")

if not SERVICE_KEY:
    print("SERVICE_KEY не найден в .env файле!")
    print("Пожалуйста, добавьте SERVICE_KEY в .env файл")
    print("Получить его можно в Supabase Dashboard -> Settings -> API -> service_role key")
    exit(1)

print(f"SERVICE_KEY: {SERVICE_KEY[:20]}...")

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

# Обновляем роль через SERVICE_KEY
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
update_data = {
    "role": "employer",
    "full_name": "Тестовый Работодатель",
    "city": "Москва",
    "religion": "не указано"
}

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

print(f"\n=== Обновление роли пользователя {user_id} на employer ===")

try:
    resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print(f"\nSUCCESS: Роль обновлена на employer!")
    else:
        print(f"\nERROR: Не удалось обновить роль")
        print(f"Response: {resp.text}")
except Exception as e:
    print(f"Ошибка: {e}")

# Проверка
print("\n=== Проверка профиля ===")
profile_check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
headers_check = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
}

try:
    resp_check = requests.get(profile_check_url, headers=headers_check, timeout=10)
    print(f"Status: {resp_check.status_code}")
    print(f"Response: {resp_check.text}")
    
    if resp_check.status_code == 200:
        data = resp_check.json()
        if data:
            user = data[0]
            print(f"\nUser ID: {user.get('id')}")
            print(f"Role: {user.get('role')}")
            print(f"Full Name: {user.get('full_name')}")
            
            if user.get('role') == 'employer':
                print(f"\nSUCCESS: Роль успешно обновлена на employer!")
            else:
                print(f"\nWARNING: Роль все еще {user.get('role')}")
        else:
            print("Пользователь не найден")
except Exception as e:
    print(f"Ошибка проверки: {e}")
