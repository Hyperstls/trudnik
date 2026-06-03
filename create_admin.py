import requests
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_ANON_KEY: {SUPABASE_ANON_KEY[:20]}...")
print(f"SERVICE_KEY: {SERVICE_KEY[:20] if SERVICE_KEY else 'NOT SET'}...")

# Создание пользователя через signup
email = "test_admin@test.com"
password = "Test123456"

signup_url = f"{SUPABASE_URL}/auth/v1/signup"
resp = requests.post(
    signup_url,
    json={"email": email, "password": password},
    headers={"apikey": SUPABASE_ANON_KEY},
    timeout=10
)

print(f"\nSignup status: {resp.status_code}")
print(f"Signup response: {resp.json()}")

if resp.ok:
    user_id = resp.json()['user']['id']
    print(f"User ID: {user_id}")
    
    # Обновление роли через SERVICE_KEY
    if SERVICE_KEY:
        update_url = f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}"
        update_data = {
            "role": "admin",
            "full_name": "Test Admin",
            "city": "Москва"
        }
        resp = requests.patch(
            update_url,
            json=update_data,
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        print(f"Update status: {resp.status_code}")
        print(f"Update response: {resp.json()}")
    else:
        print("SERVICE_KEY is not set")
