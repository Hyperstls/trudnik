"""Check jobs table and create test job directly"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print(f"Testing with URL: {SUPABASE_URL}")
print(f"SERVICE_KEY present: {bool(SERVICE_KEY)}")

# Попытка создать задание напрямую через API
headers = {
    'apikey': SERVICE_KEY if SERVICE_KEY else SUPABASE_ANON_KEY,
    'Authorization': f'Bearer {SERVICE_KEY if SERVICE_KEY else SUPABASE_ANON_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
}

job_data = {
    'employer_id': 'c6291021-7741-4a10-b68c-b1c7ec002442',
    'organization_name': 'Test Organization Direct',
    'org_description': 'Direct test',
    'object_description': 'Direct test object',
    'work_type': 'Test work',
    'detailed_description': 'Direct test description',
    'date_time': '2026-06-15T10:00:00',
    'payment_amount': 5000,
    'address': 'Moscow',
    'city': 'Moscow',
    'lat': 55.75,
    'lng': 37.61,
    'preferred_religion': 'не важно',
}

url = f"{SUPABASE_URL}/rest/v1/jobs"
print(f"\nAttempting to create job at: {url}")
print(f"Headers: {headers}")

try:
    if SERVICE_KEY:
        print("\nUsing SERVICE_KEY (with RLS bypass)...")
        resp = requests.post(url, json=job_data, headers=headers, timeout=10)
    else:
        print("\nUsing ANON_KEY (with RLS)...")
        resp = requests.post(url, json=job_data, headers=headers, timeout=10)
    
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
    
    if resp.ok:
        print("\n[SUCCESS] Job created successfully!")
    else:
        print(f"\n[FAIL] Job creation failed")
        
except Exception as e:
    print(f"Error: {e}")

# Проверка таблицы jobs
print("\nChecking jobs table...")
jobs_url = f"{SUPABASE_URL}/rest/v1/jobs?select=*&limit=1"
try:
    resp = requests.get(jobs_url, headers=headers, timeout=10)
    print(f"Jobs table status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        print(f"Jobs count: {len(data) if isinstance(data, list) else 'N/A'}")
        if data:
            print(f"Sample job: {data[0] if isinstance(data, list) else data}")
except Exception as e:
    print(f"Error checking jobs: {e}")
