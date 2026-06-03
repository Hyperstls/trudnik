import requests
import json

SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_KEY = "***REMOVED***"

# Регистрация нового пользователя
signup_url = f"{SUPABASE_URL}/auth/v1/signup"
payload = {
    "email": "test_employer_final@test.com",
    "password": "123456"
}
headers = {
    'apikey': SUPABASE_KEY,
    'Content-Type': 'application/json',
}

print("=== Регистрация нового пользователя ===")
print(f"URL: {signup_url}")
print(f"Payload: {payload}")

try:
    resp = requests.post(signup_url, json=payload, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"\n✓ Регистрация успешна!")
        user_id = data.get('user', {}).get('id')
        print(f"  User ID: {user_id}")
        print(f"  Email: {data.get('user', {}).get('email')}")
        
        # Обновление профиля с ролью employer
        if user_id:
            profile_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
            profile_data = {
                "role": "employer",
                "full_name": "Тестовый Работодатель",
                "city": "Москва",
                "religion": "не указано"
            }
            
            headers_patch = {
                'apikey': SUPABASE_KEY,
                'Authorization': f'Bearer {SUPABASE_KEY}',
                'Content-Type': 'application/json',
                'Prefer': 'return=representation'
            }
            
            print(f"\n=== Обновление профиля с ролью employer ===")
            print(f"Profile data: {profile_data}")
            
            resp_patch = requests.patch(profile_url, json=profile_data, headers=headers_patch, timeout=10)
            print(f"Patch Status: {resp_patch.status_code}")
            print(f"Patch Response: {resp_patch.text}")
            
            if resp_patch.status_code == 200:
                print("\n✓ Профиль обновлен с ролью employer!")
            else:
                print("\n✗ Ошибка обновления профиля")
                
    else:
        print(f"\n✗ Ошибка регистрации")
        error_data = resp.json() if resp.headers.get('content-type') and 'application/json' in resp.headers.get('content-type') else {}
        print(f"  Response: {error_data}")
except Exception as e:
    print(f"Ошибка: {e}")
