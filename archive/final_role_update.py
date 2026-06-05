"""
Финальный скрипт для обновления роли пользователя
RLS должен быть отключен в Supabase Dashboard
"""

import requests
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "SUPABASE_URL и SUPABASE_ANON_KEY должны быть установлены "
        "в переменных окружения."
    )

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
update_data = {
    "role": "employer",
    "full_name": "Тестовый Работодатель"
}

print("=== Финальное обновление роли ===")
print(f"User ID: {user_id}")
print(f"Новая роль: {update_data['role']}")
print()

# Попытка 1: Использовать анонимный ключ с RLS отключенным
print("Попытка 1: Обновление через анонимный ключ (RLS отключен)")
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
print(f"URL: {profile_url}")
print(f"Headers: {json.dumps(headers, indent=2)}")
print(f"Data: {json.dumps(update_data, indent=2)}")

try:
    resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("\nSUCCESS: Роль обновлена!")
        result = resp.json()
        print(f"Обновленный профиль: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"\nERROR: Не удалось обновить роль (код {resp.status_code})")
        print("Проверьте, что RLS отключен в Supabase Dashboard")
        print("Settings -> Table Editor -> profiles -> Table Settings -> Row Level Security -> Disable")
        
except Exception as e:
    print(f"Ошибка: {e}")

# Проверка
print("\n=== Проверка результата ===")
check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
resp_check = requests.get(check_url, headers={'apikey': SUPABASE_KEY}, timeout=10)

if resp_check.status_code == 200:
    data = resp_check.json()
    if data:
        user = data[0]
        print(f"User ID: {user.get('id')}")
        print(f"Role: {user.get('role')}")
        print(f"Full Name: {user.get('full_name')}")
        
        if user.get('role') == 'employer':
            print("\n✅ SUCCESS: Роль успешно обновлена на 'employer'!")
        else:
            print(f"\n❌ ERROR: Роль остается '{user.get('role')}', ожидался 'employer'")
    else:
        print("Пользователь не найден")
else:
    print(f"Ошибка проверки: {resp_check.status_code}")
