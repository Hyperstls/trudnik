"""
Скрипт для обновления роли пользователя через Flask API на PythonAnywhere
Без использования SERVICE_KEY
"""

import requests

# Настройки
BASE_URL = "https://hyperstls.pythonanywhere.com"

# Данные пользователя
user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
email = "test_employer_final@test.com"
password = "123456"

print("=== Обновление роли через Flask API ===")
print(f"BASE_URL: {BASE_URL}")
print(f"User ID: {user_id}")
print()

# Шаг 1: Войти в систему
print("Шаг 1: Вход в систему...")
login_url = f"{BASE_URL}/login"
login_data = {
    "email": email,
    "password": password
}

try:
    resp = requests.post(login_url, data=login_data, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Cookies: {resp.cookies.get_dict()}")
    
    if resp.status_code != 200:
        print(f"Ошибка входа: {resp.text}")
        exit(1)
    
    print("Успешный вход!")
    
except Exception as e:
    print(f"Ошибка: {e}")
    exit(1)

# Шаг 2: Проверить текущую роль
print("\nШаг 2: Проверка текущей роли...")
profile_url = f"{BASE_URL}/api/profile"

try:
    resp = requests.get(profile_url, cookies=resp.cookies, timeout=10)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"Текущая роль: {data.get('role', 'не установлена')}")
    else:
        print(f"Не удалось получить профиль: {resp.text}")
        
except Exception as e:
    print(f"Ошибка: {e}")

# Шаг 3: Попытаться обновить роль через прямой запрос к Supabase
print("\nШаг 3: Прямое обновление роли через Supabase REST API...")
supabase_url = "https://***REMOVED***.supabase.co/rest/v1/profiles"

# Получаем access_token из cookies
access_token = resp.cookies.get('supabase-auth-token')

if access_token:
    headers = {
        'apikey': access_token,  # Используем access_token вместо анонимного ключа
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    update_data = {
        "role": "employer",
        "full_name": "Тестовый Работодатель"
    }
    
    try:
        resp = requests.patch(
            f"{supabase_url}?id=eq.{user_id}",
            json=update_data,
            headers=headers,
            timeout=10
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code == 200:
            print("SUCCESS: Роль обновлена через access_token!")
        else:
            print(f"ERROR: Не удалось обновить роль (код {resp.status_code})")
            print("Возможно, RLS блокирует запрос")
            
    except Exception as e:
        print(f"Ошибка: {e}")
else:
    print("access_token не найден в cookies")
