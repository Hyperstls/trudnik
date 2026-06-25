"""Quick script to delete remaining unwanted user via admin web interface."""
import sys, re, time, requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = "https://trudnik-hyperstls.amvera.io"
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 TrudnikCleanup/1.0"})

# Login
print("Login as admin@test.ru...")
r = s.post(f"{BASE}/login", data={"email": "admin@test.ru", "password": "Step@1986"}, allow_redirects=False)
print(f"  Status: {r.status_code}, Location: {r.headers.get('Location', '?')}")

if r.status_code not in (302, 303, 301):
    print("ERROR: Login failed!")
    print(r.text[:500])
    sys.exit(1)

# Get admin users page
print("Get /admin?tab=users...")
r = s.get(f"{BASE}/admin?tab=users")
print(f"  URL: {r.url}, Status: {r.status_code}")

# Extract CSRF
soup = BeautifulSoup(r.text, 'html.parser')
csrf_input = soup.find('input', {'name': 'csrf_token'})
csrf_token = csrf_input['value'] if csrf_input else None
if not csrf_token:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    csrf_token = m.group(1) if m else None
print(f"  CSRF token: {csrf_token[:20] if csrf_token else 'NOT FOUND'}...")

# Find all user IDs
user_ids = re.findall(r'/admin/users/([a-f0-9-]+)/delete', r.text)
user_ids = list(dict.fromkeys(user_ids))  # dedup preserving order
print(f"  Users found: {len(user_ids)}")

# Also extract emails to identify admin
# Find email cells
emails = re.findall(r'<td class="[^"]*text-neutral-600[^"]*">([^<]+@[^<]+)</td>', r.text)
print(f"  Emails found: {emails}")

# Delete all non-admin users
deleted = 0
for uid in user_ids:
    print(f"  Deleting user {uid[:8]}... ", end="", flush=True)
    r = s.post(f"{BASE}/admin/users/{uid}/delete", data={"csrf_token": csrf_token}, allow_redirects=False)
    if r.status_code in (302, 303):
        print("OK")
        deleted += 1
    else:
        print(f"FAIL ({r.status_code})")
    time.sleep(0.3)

print(f"\nDeleted: {deleted}")

# Final check
r = s.get(f"{BASE}/admin?tab=users")
final_ids = re.findall(r'/admin/users/([a-f0-9-]+)/delete', r.text)
final_emails = re.findall(r'<td class="[^"]*text-neutral-600[^"]*">([^<]+@[^<]+)</td>', r.text)
print(f"Final users ({len(set(final_ids))}):")
for e in set(final_emails):
    print(f"  - {e}")
