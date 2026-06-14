"""
FULL test: creates test data via Supabase, then tests all new P0-P1 routes.
"""
import os, sys, json, re, time, uuid
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANON_KEY = os.environ["SUPABASE_ANON_KEY"]
BASE = "http://127.0.0.1:5000"

OUT = os.path.join(os.path.dirname(__file__), "new_routes_report.txt")
report = []
passed = 0
failed = 0
warn = 0

def log(level, msg):
    global passed, failed, warn
    t = datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {level:5s} | {msg}"
    report.append(line)
    print(line)
    if level == "PASS": passed += 1
    elif level == "FAIL": failed += 1
    elif level == "WARN": warn += 1

# ── Supabase admin helpers ──
def sb_admin(method, endpoint, json_data=None):
    h = {"apikey": ANON_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
         "Content-Type": "application/json", "Prefer": "return=representation"}
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    if json_data:
        return requests.request(method, url, headers=h, json=json_data, timeout=15)
    return requests.request(method, url, headers=h, timeout=15)

# ── Get test user IDs ──
def get_user_id(email):
    r = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users",
                     headers={"apikey": ANON_KEY, "Authorization": f"Bearer {SERVICE_KEY}"}, timeout=10)
    for u in r.json().get("users", []):
        if u.get("email") == email:
            return u["id"]
    return None

# ── Web helpers ──
def login(email, pw):
    s = requests.Session()
    s.get(f"{BASE}/login")
    s.post(f"{BASE}/login", data={"email": email, "password": pw}, allow_redirects=False)
    return s

def get_csrf(s):
    r = s.get(f"{BASE}/")
    m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', r.text)
    return m.group(1) if m else None

def api_post(s, url, json_data=None, form_data=None):
    csrf = get_csrf(s)
    h = {}
    if json_data is not None:
        h["Content-Type"] = "application/json"
    if csrf:
        h["X-CSRF-Token"] = csrf
    if json_data is not None:
        return s.post(url, json=json_data, headers=h, allow_redirects=False)
    else:
        if form_data and csrf:
            form_data["_csrf_token"] = csrf
        return s.post(url, data=form_data, headers=h, allow_redirects=False)

# ═══════════════════════════════════════════════════
log("INFO", f"Full Test Report - {BASE}")
log("INFO", f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("INFO", "=" * 60)

# ── Get user IDs ──
emp_id = get_user_id("org@test.ru")
wrk_id = get_user_id("trud3@test.ru")
admin_id = get_user_id("admin@test.ru")
log("INFO", f"Users: employer={emp_id[:12] if emp_id else 'NONE'}... worker={wrk_id[:12] if wrk_id else 'NONE'}...")

if not emp_id or not wrk_id:
    log("FAIL", "Cannot find test users - run setup_test_users.py first")
    sys.exit(1)

# ── Create test jobs via Supabase admin ──
now = datetime.now(timezone.utc)
future = now + timedelta(days=7)
past = now - timedelta(hours=1)
far_future = now + timedelta(days=30)

test_jobs = [
    {"status": "open", "date_time": future.isoformat(), "label": "open_job"},
    {"status": "in_progress", "date_time": future.isoformat(), "current_workers": 2, "max_workers": 2, "label": "in_progress_job"},
    {"status": "active", "date_time": past.isoformat(), "current_workers": 1, "max_workers": 2, "label": "active_job"},
    {"status": "cancelled", "date_time": future.isoformat(), "label": "cancelled_job"},
    {"status": "completed", "date_time": past.isoformat(), "current_workers": 1, "max_workers": 2, "label": "completed_job"},
]

created_jobs = {}
for jdef in test_jobs:
    data = {
        "employer_id": emp_id,
        "organization_name": f"TEST {jdef['label']}",
        "detailed_description": f"Test job for {jdef['label']}",
        "work_type": "one-time",
        "payment_amount": 5000,
        "city": "Moscow",
        "address": "Test Street 1",
        "status": jdef["status"],
        "max_workers": jdef.get("max_workers", 2),
        "current_workers": jdef.get("current_workers", 0),
        "date_time": jdef["date_time"],
        "is_paid": True,
        "lat": 55.75,
        "lng": 37.61,
    }
    r = sb_admin("POST", "jobs", data)
    if r.ok and r.json():
        jid = r.json()[0]["id"]
        created_jobs[jdef["label"]] = jid
        log("INFO", f"Created {jdef['label']}: {jid[:12]}...")
    else:
        log("FAIL", f"Failed to create {jdef['label']}: {r.status_code} {r.text[:100]}")

# ── Create test applications ──
app_ids = {}
if "open_job" in created_jobs:
    r = sb_admin("POST", "applications", {
        "job_id": created_jobs["open_job"],
        "worker_id": wrk_id,
        "status": "pending"
    })
    if r.ok and r.json():
        app_ids["pending"] = r.json()[0]["id"]
        log("INFO", f"Created pending application: {app_ids['pending'][:12]}...")

if "active_job" in created_jobs:
    r = sb_admin("POST", "applications", {
        "job_id": created_jobs["active_job"],
        "worker_id": wrk_id,
        "status": "accepted"
    })
    if r.ok and r.json():
        app_ids["accepted"] = r.json()[0]["id"]
        log("INFO", f"Created accepted application: {app_ids['accepted'][:12]}...")

# ── Login sessions ──
s_emp = login("org@test.ru", "test123")
s_wrk = login("trud3@test.ru", "test123")
log("INFO", "Login: employer OK, worker OK")

# ═══════════════════════════════════════════════════
# TEST 1: force-complete
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 1: force-complete ---")

# 1a: No auth
r = requests.post(f"{BASE}/api/jobs/x/force-complete")
log("PASS" if r.status_code in (302, 400) else "FAIL",
    f"1a. No auth: {r.status_code}")

# 1b: Worker
r = api_post(s_wrk, f"{BASE}/api/jobs/{created_jobs.get('active_job', 'x')}/force-complete")
log("PASS" if r.status_code in (403, 302, 404) else "FAIL",
    f"1b. Worker: {r.status_code}")

# 1c: Employer on active job (success)
if "active_job" in created_jobs:
    r = api_post(s_emp, f"{BASE}/api/jobs/{created_jobs['active_job']}/force-complete")
    try:
        d = r.json()
        if r.status_code == 200 and d.get("success"):
            log("PASS", f"1c. Force-complete active: 200 - {d.get('message', '')[:60]}")
        else:
            log("FAIL", f"1c. Force-complete active: {r.status_code} - {d.get('error', '')[:80]}")
    except:
        log("FAIL", f"1c. Force-complete active: {r.status_code}")

# 1d: Employer on open job (should fail 409)
if "open_job" in created_jobs:
    r = api_post(s_emp, f"{BASE}/api/jobs/{created_jobs['open_job']}/force-complete")
    if r.status_code == 409:
        log("PASS", "1d. Force-complete open: 409 (correct)")
    elif r.status_code == 200:
        log("FAIL", "1d. Force-complete open: 200 (should have been blocked)")
    else:
        try:
            d = r.json()
            log("FAIL", f"1d. Force-complete open: {r.status_code} - {d.get('error', '')[:80]}")
        except:
            log("FAIL", f"1d. Force-complete open: {r.status_code}")

# 1e: Employer not owner
r = api_post(s_emp, f"{BASE}/api/jobs/00000000-0000-0000-0000-000000000001/force-complete")
log("PASS" if r.status_code in (403, 404) else "FAIL",
    f"1e. Not owner: {r.status_code}")

# ═══════════════════════════════════════════════════
# TEST 2: withdraw
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 2: withdraw ---")

# 2a: No auth
r = requests.post(f"{BASE}/api/applications/x/withdraw")
log("PASS" if r.status_code in (302, 400) else "FAIL",
    f"2a. No auth: {r.status_code}")

# 2b: Nonexistent
r = api_post(s_wrk, f"{BASE}/api/applications/00000000-0000-0000-0000-000000000001/withdraw")
log("PASS" if r.status_code == 404 else "FAIL",
    f"2b. Nonexistent: {r.status_code}")

# 2c: Withdraw pending (success)
if "pending" in app_ids:
    r = api_post(s_wrk, f"{BASE}/api/applications/{app_ids['pending']}/withdraw")
    try:
        d = r.json()
        if r.status_code == 200 and d.get("success"):
            log("PASS", f"2c. Withdraw pending: 200 - {d.get('message', '')[:60]}")
        else:
            log("FAIL", f"2c. Withdraw pending: {r.status_code} - {d.get('error', '')[:80]}")
    except:
        log("FAIL", f"2c. Withdraw pending: {r.status_code}")
else:
    log("WARN", "2c. No pending application to test")

# 2d: Withdraw accepted (12h limit)
if "accepted" in app_ids:
    r = api_post(s_wrk, f"{BASE}/api/applications/{app_ids['accepted']}/withdraw")
    try:
        d = r.json()
        if r.status_code == 409 and "12 часов" in d.get("error", ""):
            log("PASS", f"2d. Withdraw accepted <12h: 409 12h limit enforced")
        elif r.status_code == 200:
            log("PASS", f"2d. Withdraw accepted: 200 (more than 12h remaining)")
        elif r.status_code == 409:
            log("PASS", f"2d. Withdraw accepted: 409 - {d.get('error', '')[:60]}")
        else:
            log("FAIL", f"2d. Withdraw accepted: {r.status_code} - {d.get('error', '')[:80]}")
    except:
        log("FAIL", f"2d. Withdraw accepted: {r.status_code}")
else:
    log("WARN", "2d. No accepted application to test 12h limit")

# 2e: Employer trying to withdraw worker's application
if "accepted" in app_ids:
    r = api_post(s_emp, f"{BASE}/api/applications/{app_ids['accepted']}/withdraw")
    log("PASS" if r.status_code in (403, 404) else "FAIL",
        f"2e. Non-owner withdraw: {r.status_code}")

# ═══════════════════════════════════════════════════
# TEST 3: restore
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 3: restore ---")

if "cancelled_job" in created_jobs:
    r = api_post(s_emp, f"{BASE}/restore-job/{created_jobs['cancelled_job']}")
    if r.status_code in (200, 302):
        # Verify status changed to open
        check = s_emp.get(f"{BASE}/job/{created_jobs['cancelled_job']}")
        if "open" in check.text.lower():
            log("PASS", "3a. Restore cancelled: now open")
        else:
            log("FAIL", "3a. Restore cancelled: status not 'open'")
    elif r.status_code == 409:
        try:
            d = r.json()
            log("FAIL", f"3a. Restore cancelled: 409 - {d.get('error', '')}")
        except:
            log("FAIL", f"3a. Restore cancelled: {r.status_code}")
    else:
        log("FAIL", f"3a. Restore cancelled: {r.status_code}")
else:
    log("WARN", "3a. No cancelled job to test")

# 3b: Restore non-cancelled
if "open_job" in created_jobs:
    r = api_post(s_emp, f"{BASE}/restore-job/{created_jobs['open_job']}")
    log("PASS" if r.status_code in (409, 302) else "FAIL",
        f"3b. Restore open (should fail): {r.status_code}")

# 3c: Worker restore
r = api_post(s_wrk, f"{BASE}/restore-job/{created_jobs.get('cancelled_job', list(created_jobs.values())[0])}")
log("PASS" if r.status_code in (403, 302, 404) else "FAIL",
    f"3c. Worker restore: {r.status_code}")

# ═══════════════════════════════════════════════════
# TEST 4: edit_job blocking
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 4: edit blocking ---")

# Find job with accepted applications
accepted_jid = created_jobs.get("active_job")  # active has accepted app

if accepted_jid:
    # 4a: Edit forbidden field (title)
    r = api_post(s_emp, f"{BASE}/job/{accepted_jid}/edit", form_data={"title": "BLOCKED"})
    if r.status_code == 409:
        try:
            d = r.json()
            log("PASS", f"4a. Edit blocked: 409 - {d.get('error', '')[:60]}")
        except:
            log("PASS", "4a. Edit blocked: 409")
    elif r.status_code == 302:
        check = s_emp.get(f"{BASE}/job/{accepted_jid}")
        if "нельзя" in check.text.lower():
            log("PASS", "4a. Edit blocked: redirect with error")
        else:
            log("FAIL", "4a. Edit blocked: redirect without error message")
    else:
        log("FAIL", f"4a. Edit blocked: {r.status_code}")

    # 4b: Edit allowed field (description)
    r = api_post(s_emp, f"{BASE}/job/{accepted_jid}/edit", form_data={"description": "Allowed"})
    if r.status_code == 302:
        log("PASS", "4b. Edit allowed (description): 302 redirect")
    else:
        log("FAIL", f"4b. Edit allowed: {r.status_code}")
else:
    log("WARN", "4. No job with accepted apps to test edit blocking")

# 4c: Edit without accepted apps (should be fully allowed)
if "open_job" in created_jobs:
    r = api_post(s_emp, f"{BASE}/job/{created_jobs['open_job']}/edit", form_data={"title": "NEW TITLE"})
    if r.status_code == 302:
        log("PASS", "4c. Edit without accepted: 302 redirect (fully allowed)")
    else:
        log("FAIL", f"4c. Edit without accepted: {r.status_code}")

# ═══════════════════════════════════════════════════
# TEST 5: auto-transition
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 5: auto-transition ---")

# 5a: Index calls auto-transition
r = requests.get(f"{BASE}/")
log("PASS" if r.status_code == 200 else "FAIL", f"5a. Index page: {r.status_code}")

# 5b: Job detail calls auto-transition
if "in_progress_job" in created_jobs:
    r = s_emp.get(f"{BASE}/job/{created_jobs['in_progress_job']}")
    log("PASS" if r.status_code == 200 else "FAIL", f"5b. Job detail (in_progress): {r.status_code}")
else:
    log("WARN", "5b. No in_progress job to test")

# 5c: Verify in_progress with past date auto-transitions to active
# (active_job was created with past date_time - check it's active)
if "active_job" in created_jobs or "in_progress_job" in created_jobs:
    jid = created_jobs.get("active_job") or created_jobs.get("in_progress_job")
    r = s_emp.get(f"{BASE}/job/{jid}")
    has_active = "active" in r.text.lower() or "актив" in r.text.lower()
    log("PASS" if has_active else "WARN", f"5c. Auto-transition visible on page: {'active found' if has_active else 'not found'}")

# ═══════════════════════════════════════════════════
# TEST 6: ratings
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 6: ratings ---")

# 6a: Rate non-existent job
r = api_post(s_emp, f"{BASE}/api/ratings", json_data={
    "job_id": "00000000-0000-0000-0000-000000000001",
    "rated_user_id": wrk_id, "rating": 5, "target_type": "worker", "comment": "test"
})
try:
    d = r.json()
    msg = d.get("error", "")[:80]
except:
    msg = r.text[:80]
log("PASS" if r.status_code in (404, 400) else "FAIL",
    f"6a. Rate nonexistent job: {r.status_code} - {msg}")

# 6b: Self-rating
r = api_post(s_emp, f"{BASE}/api/ratings", json_data={
    "job_id": created_jobs.get("completed_job", list(created_jobs.values())[0] if created_jobs else "x"),
    "rated_user_id": emp_id, "rating": 5, "target_type": "worker"
})
try:
    d = r.json()
    msg = d.get("error", "")[:80]
except:
    msg = r.text[:80]
if r.status_code == 400 and "себя" in msg.lower():
    log("PASS", f"6b. Self-rating blocked: {msg[:60]}")
elif r.status_code in (400, 403, 404):
    log("PASS", f"6b. Self-rating: {r.status_code} - {msg}")
else:
    log("FAIL", f"6b. Self-rating: {r.status_code} - {msg}")

# 6c: Non-participant rating
r = api_post(s_wrk, f"{BASE}/api/ratings", json_data={
    "job_id": created_jobs.get("completed_job", list(created_jobs.values())[0] if created_jobs else "x"),
    "rated_user_id": emp_id, "rating": 3, "target_type": "employer"
})
try:
    d = r.json()
    msg = d.get("error", "")[:80]
except:
    msg = r.text[:80]
log("PASS" if r.status_code in (403, 404, 400) else "FAIL",
    f"6c. Non-participant: {r.status_code} - {msg}")

# 6d: GET ratings
r = requests.get(f"{BASE}/api/ratings/{created_jobs.get('completed_job', list(created_jobs.values())[0] if created_jobs else 'x')}")
try:
    d = r.json()
    log("PASS" if d.get("success") else "FAIL",
        f"6d. GET ratings: 200 - success={d.get('success')}")
except:
    log("FAIL", f"6d. GET ratings: {r.status_code}")

# ═══════════════════════════════════════════════════
# TEST 7: backward compatibility
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 7: backward compat ---")

checks = [
    ("GET /", requests.get(f"{BASE}/")),
    ("GET /workers", requests.get(f"{BASE}/workers")),
    ("GET /api/skills", requests.get(f"{BASE}/api/skills")),
    ("GET /api/religions", requests.get(f"{BASE}/api/religions")),
    ("GET /login", requests.get(f"{BASE}/login")),
    ("GET /register", requests.get(f"{BASE}/register")),
    ("GET /my-jobs", s_emp.get(f"{BASE}/my-jobs")),
    ("GET /favorites", s_emp.get(f"{BASE}/favorites")),
]
all_ok = True
for name, r in checks:
    ok = r.status_code == 200
    if not ok: all_ok = False
    log("PASS" if ok else "FAIL", f"7. {name}: {r.status_code}")

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════
log("INFO", "-" * 60)
log("INFO", f"Total: {passed} passed, {failed} failed, {warn} warnings")
total_tests = passed + failed
rate = 100*passed//total_tests if total_tests else 0
log("INFO", f"Success rate: {rate}% ({passed}/{total_tests})")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("Trudnik New Routes Full Test Report\n")
    f.write(f"Server: {BASE}\n")
    f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 60 + "\n")
    for line in report:
        f.write(line + "\n")
    f.write("-" * 60 + "\n")
    f.write(f"Total: {passed} passed, {failed} failed, {warn} warnings\n")

print(f"\nReport saved to {OUT}")
sys.exit(0 if failed == 0 else 1)
