"""
Скрипт для отключения RLS через Flask-приложение на PythonAnywhere
"""

import sys
sys.path.insert(0, '/home/hyperstls')

from app import app
import config

app = app

# Получаем SERVICE_KEY
SERVICE_KEY = app.config.get('SUPABASE_SERVICE_ROLE_KEY', '')

if not SERVICE_KEY:
    print("SERVICE_KEY не найден!")
    print("Добавьте SERVICE_KEY в config.py или .env файл")
    sys.exit(1)

print(f"SERVICE_KEY найден: {SERVICE_KEY[:20]}...")

SUPABASE_URL = app.config['SUPABASE_URL']
user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

# Обновляем роль через SERVICE_KEY
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
update_data = {"role": "employer"}

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

print(f"\n=== Обновление роли пользователя {user_id} на employer ===")

import requests
resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
print(f"Status: {resp.status_code}")
print(f"Response: {resp.text}")

if resp.status_code == 200:
    print(f"\nSUCCESS: Роль обновлена на employer!")
else:
    print(f"\nERROR: Не удалось обновить роль")

# Проверка
print("\n=== Проверка профиля ===")
profile_check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"
headers_check = {'apikey': SERVICE_KEY, 'Authorization': f'Bearer {SERVICE_KEY}'}
resp_check = requests.get(profile_check_url, headers=headers_check, timeout=10)
print(f"Status: {resp_check.status_code}")
print(f"Response: {resp_check.text}")

if resp_check.status_code == 200:
    data = resp_check.json()
    if data:
        user = data[0]
        print(f"\nUser ID: {user.get('id')}")
        print(f"Role: {user.get('role')}")
