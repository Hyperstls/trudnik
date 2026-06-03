"""Check if job was created via direct API"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

headers = {
    'apikey': SUPABASE_ANON_KEY,
    'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
}

url = f"{SUPABASE_URL}/rest/v1/jobs?select=*&order=created_at.desc&limit=5"
print(f"Checking jobs table...")

try:
    resp = requests.get(url, headers=headers, timeout=10)
    print(f"Status: {resp.status_code}")
    
    if resp.ok:
        jobs = resp.json()
        print(f"Jobs found: {len(jobs)}")
        for job in jobs:
            print(f"  - {job.get('organization_name', 'N/A')}: {job.get('payment_amount', 'N/A')} руб.")
    else:
        print(f"Error: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
