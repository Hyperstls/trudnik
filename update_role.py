"""
Скрипт для обновления роли пользователя в базе данных Supabase через Flask-приложение
Запускать на PythonAnywhere после добавления SERVICE_KEY в config.py

Инструкция:
1. Добавить SERVICE_KEY в .env файл на PythonAnywhere:
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...

2. Загрузить этот скрипт на PythonAnywhere:
   https://hyperstls.pythonanywhere.com/update_role.py

3. Выполнить скрипт через curl или в браузере
"""

from flask import Flask, request, jsonify
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/home/hyperstls')

from app import app
import config

app = Flask(__name__)
app.config.from_object(config.Config)

SUPABASE_URL = app.config['SUPABASE_URL']
SERVICE_KEY = app.config.get('SUPABASE_SERVICE_ROLE_KEY', '')

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
role = "employer"

print(f"SERVICE_KEY: {SERVICE_KEY[:20] if SERVICE_KEY else 'NOT SET'}...")

if not SERVICE_KEY:
    print("SERVICE_KEY не найден! Обновление невозможно.")
    print("Пожалуйста, добавьте SERVICE_KEY в config.py или .env файл")
    sys.exit(1)

# Обновляем роль через SERVICE_KEY
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
update_data = {"role": role}

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

print(f"\n=== Обновление роли пользователя {user_id} на {role} ===")

try:
    resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print(f"\nSUCCESS: Роль обновлена на {role}!")
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
        else:
            print("Пользователь не найден")
except Exception as e:
    print(f"Ошибка проверки: {e}")
