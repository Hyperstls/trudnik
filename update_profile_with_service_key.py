import requests
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

if not SERVICE_KEY:
    print("SERVICE_KEY не найден в .env")
    exit(1)

print(f"SERVICE_KEY найден: {SERVICE_KEY[:20]}...")

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

# Обновление профиля с ролью employer через SERVICE_KEY
profile_update_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
update_data = {"role": "employer", "full_name": "Тестовый Работодатель", "city": "Москва", "religion": "не указано"}

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

print("\n=== Обновление профиля через SERVICE_KEY ===")
print(f"Update data: {update_data}")

resp = requests.patch(profile_update_url, json=update_data, headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

if resp.status_code == 200:
    print("\nSUCCESS: Профиль обновлен с ролью employer!")
else:
    print(f"\nERROR: Не удалось обновить профиль")

# Проверка
print("\n=== Проверка профиля ===")
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
resp_check = requests.get(profile_url, headers={'apikey': SERVICE_KEY, 'Authorization': f'Bearer {SERVICE_KEY}'}, timeout=10)
print(f"Status: {resp_check.status_code}")
print(f"Response: {resp_check.text}")
