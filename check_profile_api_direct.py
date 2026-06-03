import sys
import io
import requests
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')

# Вход
auth_url = f'{SUPABASE_URL}/auth/v1/token?grant_type=password'
resp = requests.post(
    auth_url,
    json={'email': 'test_admin@test.com', 'password': 'Test123456'},
    headers={'apikey': SUPABASE_ANON_KEY},
    timeout=10
)

print(f"Auth status: {resp.status_code}")
print(f"Auth response: {resp.json()}")

if resp.ok:
    data = resp.json()
    user_id = data['user']['id']
    print(f"User ID: {user_id}")
    print(f"Email: {data['user']['email']}")
    
    # Запрос к profiles
    profiles_url = f'{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}&select=role'
    resp = requests.get(
        profiles_url,
        headers={'apikey': SUPABASE_ANON_KEY, 'Authorization': f'Bearer {data["access_token"]}'},
        timeout=10
    )
    
    print(f"\nProfiles status: {resp.status_code}")
    print(f"Profiles response: {resp.json()}")
    
    if resp.ok and resp.json():
        role = resp.json()[0].get('role', 'NOT FOUND')
        print(f"Role: {role}")
    else:
        print("No profile found")
