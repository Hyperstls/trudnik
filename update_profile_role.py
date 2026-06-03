import requests

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_KEY = "***REMOVED***"

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}

print("=== Проверка текущего профиля ===")
resp = requests.get(profile_url, headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

# Обновление профиля с ролью employer
profile_update_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
update_data = {"role": "employer", "full_name": "Тестовый Работодатель", "city": "Москва", "religion": "не указано"}

headers_update = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

print("\n=== Обновление профиля ===")
print(f"Update data: {update_data}")

resp_update = requests.patch(profile_update_url, json=update_data, headers=headers_update, timeout=10)
print(f"Status: {resp_update.status_code}")
print(f"Response: {resp_update.text}")

if resp_update.status_code == 200:
    print("\nSUCCESS: Профиль обновлен с ролью employer!")
else:
    print(f"\nERROR: Не удалось обновить профиль")
