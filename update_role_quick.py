"""
Быстрый способ обновить роль пользователя без SERVICE_KEY

Инструкция:
1. Загрузить этот скрипт на PythonAnywhere в ту же папку, что и app.py
2. Выполнить: python update_role_quick.py
3. Проверить результат

Этот скрипт использует REST API с анонимным ключом, но без RLS будет работать.
Для отключения RLS нужно выполнить SQL: ALTER TABLE profiles DISABLE ROW LEVEL SECURITY
"""

import sys
import os
import requests

# Путь к проекту
sys.path.insert(0, '/home/hyperstls')

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

print("=== Быстрое обновление роли ===")

if not SERVICE_KEY:
    print("SERVICE_KEY не найден в .env!")
    print("Попытка использовать анонимный ключ без RLS...")
    print("\nВАЖНО: RLS должен быть отключен для таблицы profiles!")
    print("Проверьте: Supabase Dashboard -> Table Editor -> profiles -> RLS")
else:
    print(f"SERVICE_KEY найден: {SERVICE_KEY[:20]}...")

user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"

# Попытка 1: Использовать SERVICE_KEY (рекомендуется)
if SERVICE_KEY:
    print("\n=== Попытка 1: Использовать SERVICE_KEY ===")
    profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
    update_data = {"role": "employer", "full_name": "Тестовый Работодатель"}
    
    headers = {
        'apikey': SERVICE_KEY,
        'Authorization': f'Bearer {SERVICE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    resp = requests.patch(profile_url, json=update_data, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("SUCCESS: Роль обновлена через SERVICE_KEY!")
    else:
        print("ERROR: Не удалось обновить через SERVICE_KEY")
else:
    print("\n=== Попытка 2: Использовать анонимный ключ (без RLS) ===")
    
    # Если SERVICE_KEY нет, используем анонимный ключ
    headers_anon = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
    update_data = {"role": "employer", "full_name": "Тестовый Работодатель"}
    
    resp = requests.patch(profile_url, json=update_data, headers=headers_anon, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        print("SUCCESS: Роль обновлена через анонимный ключ (RLS отключен)!")
    else:
        print("ERROR: Не удалось обновить роль")
        print("Возможно, RLS включен. Отключите его в Supabase Dashboard")

# Проверка
print("\n=== Проверка профиля ===")
profile_check_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=*"

if SERVICE_KEY:
    headers_check = {'apikey': SERVICE_KEY, 'Authorization': f'Bearer {SERVICE_KEY}'}
else:
    headers_check = {'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'}

resp_check = requests.get(profile_check_url, headers=headers_check, timeout=10)
print(f"Status: {resp_check.status_code}")

if resp_check.status_code == 200:
    data = resp_check.json()
    if data:
        user = data[0]
        print(f"\nUser ID: {user.get('id')}")
        print(f"Role: {user.get('role')}")
        print(f"Full Name: {user.get('full_name')}")
        
        if user.get('role') == 'employer':
            print(f"\nSUCCESS: Роль успешно обновлена на employer!")
            print("Теперь можно протестировать вход:")
            print("python my_browser_agent.py \"Войди как test_employer_final@test.com с паролем 123456\"")
        else:
            print(f"\nWARNING: Роль все еще {user.get('role')}")
    else:
        print("Пользователь не найден")
