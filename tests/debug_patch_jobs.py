"""Debug: почему PATCH jobs возвращает 400?"""
import os, requests

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    with open(dotenv_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_ANON_KEY']
SERVICE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
}

# Create a test job
r = requests.post(f'{SUPABASE_URL}/rest/v1/jobs', headers=HEADERS, json={
    'employer_id': '45debed7-54f9-44b5-925f-595dfad65373',
    'organization_name': 'DEBUG TEST',
    'payment_amount': 1000,
    'address': 'Test',
    'city': 'Test',
    'lat': 55.75,
    'lng': 37.61,
    'status': 'open',
    'max_workers': 1,
    'current_workers': 0,
    'date_time': '2026-06-10T10:00:00',
})
if r.ok:
    job_id = r.json()[0]['id']
    print(f'Created job: {job_id}')
    
    # Test various status transitions
    for status, payload in [
        ('active', {'status': 'active'}),
        ('payment_pending', {'status': 'payment_pending'}),
        ('paid', {'status': 'paid'}),
        ('completed', {'status': 'completed'}),
        ('in_progress+workers', {'status': 'in_progress', 'current_workers': 1}),
    ]:
        r2 = requests.patch(f'{SUPABASE_URL}/rest/v1/jobs?id=eq.{job_id}', headers=HEADERS, json=payload)
        print(f'PATCH {status}: status={r2.status_code} body={r2.text[:300]}')
    
    # Cleanup
    requests.delete(f'{SUPABASE_URL}/rest/v1/jobs?id=eq.{job_id}', headers=HEADERS)
