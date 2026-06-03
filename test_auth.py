import requests
import json

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_KEY = "***REMOVED***"

# Попробуем авторизовать тестового пользователя
auth_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
payload = {
    "email": "test_employer_2026@test.com",
    "password": "123456"
}
headers = {
    'apikey': SUPABASE_KEY,
    'Content-Type': 'application/json',
}

print("=== Попытка авторизации тестового пользователя ===")
print(f"URL: {auth_url}")
print(f"Payload: {payload}")

try:
    resp = requests.post(auth_url, json=payload, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n✓ Авторизация успешна!")
        print(f"  Access Token: {data.get('access_token')}")
        print(f"  User ID: {data.get('user', {}).get('id')}")
        print(f"  Email: {data.get('user', {}).get('email')}")
    else:
        print(f"\n✗ Ошибка авторизации")
        error_data = resp.json() if resp.headers.get('content-type') and 'application/json' in resp.headers.get('content-type') else {}
        print(f"  Response: {error_data}")
except Exception as e:
    print(f"Ошибка: {e}")

# Попробуем найти пользователя в базе
print("\n=== Попытка найти пользователя в profiles ===")
profile_url = f"{SUPABASE_URL}/rest/v1/profiles?select=*"
headers_profile = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}

try:
    resp = requests.get(profile_url, headers=headers_profile, timeout=10)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"Найдено пользователей: {len(data)}")
        # Ищем тестового пользователя
        for user in data:
            print(f"\n  ID: {user.get('id')}")
            print(f"  Role: {user.get('role')}")
            print(f"  Full Name: {user.get('full_name')}")
except Exception as e:
    print(f"Ошибка: {e}")
