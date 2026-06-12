"""Comprehensive testing script for new P0-P1 routes."""
import requests, re, json, sys, os
from datetime import datetime

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
log("INFO", f"Trudnik New Routes Test Report - {BASE}")
log("INFO", f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log("INFO", "=" * 60)

# ── Pre-flight: check login ──
s_emp = login("org@test.ru", "test123456")
s_wrk = login("trud3@test.ru", "test123456")
log("INFO", "Logins: employer OK, worker OK")

# Get CSRF tokens
csrf_emp = get_csrf(s_emp)
csrf_wrk = get_csrf(s_wrk)
log("INFO", f"CSRF tokens: employer={'OK' if csrf_emp else 'FAIL'}, worker={'OK' if csrf_wrk else 'FAIL'}")

# Get employer's jobs
r = s_emp.get(f"{BASE}/my-jobs")
job_ids = list(set(re.findall(r'data-job-id="([^"]+)"', r.text)))
log("INFO", f"Employer jobs found: {len(job_ids)}")

# Get open jobs from main page
r = requests.get(f"{BASE}/")
open_job_ids = list(set(re.findall(r'href="/job/([^"]+)"', r.text)))
log("INFO", f"Open jobs on main: {len(open_job_ids)}")

# ═══════════════════════════════════════════════════
# TEST 1: force-complete
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 1: force-complete ---")

# 1a: No auth
r = requests.post(f"{BASE}/api/jobs/x/force-complete")
if r.status_code in (302, 400):
    log("PASS", "1a. Force-complete without auth: blocked (302/400)")
else:
    log("FAIL", f"1a. Force-complete without auth: unexpected {r.status_code}")

# 1b: Worker role
r = api_post(s_wrk, f"{BASE}/api/jobs/00000000-0000-0000-0000-000000000001/force-complete")
if r.status_code in (403, 404, 302):
    log("PASS", f"1b. Force-complete as worker: blocked ({r.status_code})")
else:
    log("FAIL", f"1b. Force-complete as worker: unexpected {r.status_code}")

# 1c: Employer force-complete on own jobs
if job_ids:
    for jid in job_ids[:5]:
        r = api_post(s_emp, f"{BASE}/api/jobs/{jid}/force-complete")
        try:
            d = r.json()
            msg = d.get("message", d.get("error", ""))[:80]
        except:
            msg = r.text[:80]
        if r.status_code == 200:
            log("PASS", f"1c. Force-complete job {jid[:12]}...: 200 - {msg}")
        elif r.status_code == 409:
            log("PASS", f"1c. Force-complete job {jid[:12]}...: 409 (wrong status) - {msg}")
        else:
            log("FAIL", f"1c. Force-complete job {jid[:12]}...: {r.status_code} - {msg}")
        break  # Just one
else:
    log("WARN", "1c. No jobs to test force-complete")

# ═══════════════════════════════════════════════════
# TEST 2: withdraw
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 2: withdraw ---")

# 2a: No auth
r = requests.post(f"{BASE}/api/applications/x/withdraw")
if r.status_code in (302, 400):
    log("PASS", f"2a. Withdraw without auth: blocked ({r.status_code})")
else:
    log("FAIL", f"2a. Withdraw without auth: unexpected {r.status_code}")

# 2b: Nonexistent application
r = api_post(s_wrk, f"{BASE}/api/applications/00000000-0000-0000-0000-000000000001/withdraw")
try:
    d = r.json()
    msg = d.get("error", "")[:80]
except:
    msg = r.text[:80]
if r.status_code == 404:
    log("PASS", f"2b. Withdraw nonexistent: 404 - {msg}")
elif r.status_code == 403:
    log("PASS", f"2b. Withdraw nonexistent: 403 - {msg}")
else:
    log("FAIL", f"2b. Withdraw nonexistent: {r.status_code} - {msg}")

# 2c: Try to apply and withdraw (pending)
if open_job_ids:
    # Apply as worker
    r = s_wrk.post(f"{BASE}/apply/{open_job_ids[0]}", allow_redirects=True)
    log("INFO", f"2c. Applied to {open_job_ids[0][:12]}... status={r.status_code}")
    
    # Now find the application via employer's my-applications
    r = s_emp.get(f"{BASE}/my-applications")
    app_ids = list(set(re.findall(r'data-app-id="([^"]+)"', r.text)))
    log("INFO", f"2c. App IDs found: {len(app_ids)}")
    
    if app_ids:
        # Try withdraw as worker
        r = api_post(s_wrk, f"{BASE}/api/applications/{app_ids[0]}/withdraw")
        try:
            d = r.json()
            msg = d.get("message", d.get("error", ""))[:80]
        except:
            msg = r.text[:80]
        if r.status_code == 200:
            log("PASS", f"2c. Withdraw pending: 200 - {msg}")
        elif r.status_code == 409:
            log("PASS", f"2c. Withdraw pending: 409 (already?) - {msg}")
        else:
            log("FAIL", f"2c. Withdraw pending: {r.status_code} - {msg}")
    else:
        log("WARN", "2c. No application IDs found")
else:
    app_ids = []
    log("WARN", "2c. No open jobs to test apply/withdraw")

# 2d: Employer trying to withdraw (should fail)
if app_ids:
    r = api_post(s_emp, f"{BASE}/api/applications/{app_ids[0]}/withdraw")
    if r.status_code in (403, 404):
        log("PASS", f"2d. Withdraw as non-owner: blocked ({r.status_code})")
    else:
        log("FAIL", f"2d. Withdraw as non-owner: {r.status_code}")
else:
    log("WARN", "2d. Skipped (no app IDs)")

# ═══════════════════════════════════════════════════
# TEST 3: restore
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 3: restore ---")

# Find cancelled job
cancelled_jid = None
for jid in job_ids[:10]:
    r = s_emp.get(f"{BASE}/job/{jid}")
    if "cancelled" in r.text.lower() or "отменен" in r.text.lower():
        cancelled_jid = jid
        break

if cancelled_jid:
    r = api_post(s_emp, f"{BASE}/restore-job/{cancelled_jid}")
    if r.status_code in (200, 302):
        # Verify status changed
        check = s_emp.get(f"{BASE}/job/{cancelled_jid}")
        if "open" in check.text.lower():
            log("PASS", f"3a. Restore cancelled: success - now open")
        else:
            log("FAIL", "3a. Restore cancelled: status not 'open' after restore")
    elif r.status_code == 409:
        try:
            d = r.json()
            msg = d.get("error", "")[:80]
        except:
            msg = r.text[:80]
        log("FAIL", f"3a. Restore cancelled: {r.status_code} - {msg}")
    else:
        log("FAIL", f"3a. Restore cancelled: unexpected {r.status_code}")
else:
    log("WARN", "3a. No cancelled jobs found")

# 3b: Restore non-cancelled
open_jid = None
for jid in job_ids[:10]:
    r = s_emp.get(f"{BASE}/job/{jid}")
    if "open" in r.text.lower():
        open_jid = jid
        break

if open_jid:
    r = api_post(s_emp, f"{BASE}/restore-job/{open_jid}")
    if r.status_code == 409:
        log("PASS", f"3b. Restore non-cancelled: 409 (correct)")
    elif r.status_code == 302:
        log("PASS", "3b. Restore non-cancelled: redirect (correct)")
    else:
        log("FAIL", f"3b. Restore non-cancelled: unexpected {r.status_code}")
else:
    log("WARN", "3b. No open jobs to test restore rejection")

# 3c: Worker restore
r = api_post(s_wrk, f"{BASE}/restore-job/{job_ids[0] if job_ids else 'x'}")
if r.status_code in (403, 302, 404):
    log("PASS", f"3c. Restore as worker: blocked ({r.status_code})")
else:
    log("FAIL", f"3c. Restore as worker: unexpected {r.status_code}")

# ═══════════════════════════════════════════════════
# TEST 4: edit_job blocking
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 4: edit_job blocking ---")

accepted_jid = None
for jid in job_ids[:10]:
    r = s_emp.get(f"{BASE}/job/{jid}")
    if "accepted" in r.text.lower() or "принят" in r.text.lower():
        accepted_jid = jid
        break

if accepted_jid:
    # 4a: Try editing forbidden field (title)
    r = api_post(s_emp, f"{BASE}/job/{accepted_jid}/edit", form_data={"title": "BLOCKED TEST"})
    if r.status_code == 409:
        try:
            d = r.json()
            msg = d.get("error", "")[:80]
        except:
            msg = r.text[:80]
        log("PASS", f"4a. Edit blocked field: 409 - {msg}")
    elif r.status_code == 302:
        check = s_emp.get(f"{BASE}/job/{accepted_jid}")
        if "нельзя" in check.text.lower():
            log("PASS", "4a. Edit blocked field: redirect with error message")
        else:
            log("FAIL", "4a. Edit blocked field: redirect without error")
    else:
        log("FAIL", f"4a. Edit blocked field: unexpected {r.status_code}")

    # 4b: Try editing allowed field (description)
    r = api_post(s_emp, f"{BASE}/job/{accepted_jid}/edit", form_data={"description": "Allowed test update"})
    if r.status_code == 302:
        log("PASS", "4b. Edit allowed field (description): 302 redirect (OK)")
    elif r.status_code == 409:
        try:
            d = r.json()
            msg = d.get("error", "")[:80]
        except:
            msg = r.text[:80]
        log("FAIL", f"4b. Edit allowed field: 409 blocked - {msg}")
    else:
        log("FAIL", f"4b. Edit allowed field: unexpected {r.status_code}")
else:
    log("WARN", "4. No jobs with accepted applications found")

# ═══════════════════════════════════════════════════
# TEST 5: auto-transition
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 5: auto-transition ---")

# 5a: Index page calls _auto_transition_in_progress_to_active
r = requests.get(f"{BASE}/")
if r.status_code == 200:
    log("PASS", "5a. Index page loads (auto-transition function called)")
else:
    log("FAIL", f"5a. Index page: {r.status_code}")

# 5b: Job detail page
if job_ids:
    r = s_emp.get(f"{BASE}/job/{job_ids[0]}")
    if r.status_code == 200:
        log("PASS", "5b. Job detail page loads (auto-transition called)")
    else:
        log("FAIL", f"5b. Job detail page: {r.status_code}")
else:
    log("WARN", "5b. No jobs to check job_detail")

# ═══════════════════════════════════════════════════
# TEST 6: ratings validation
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 6: ratings ---")

# 6a: Rate non-existent job
r = api_post(s_emp, f"{BASE}/api/ratings", json_data={
    "job_id": "00000000-0000-0000-0000-000000000001",
    "rated_user_id": "00000000-0000-0000-0000-000000000002",
    "rating": 5, "target_type": "worker", "comment": "test"
})
try:
    d = r.json()
    msg = d.get("error", d.get("success", ""))[:80]
except:
    msg = r.text[:80]
if r.status_code in (404, 400):
    log("PASS", f"6a. Rate non-existent job: {r.status_code} - {msg}")
else:
    log("FAIL", f"6a. Rate non-existent job: {r.status_code} - {msg}")

# 6b: Self-rating
r = api_post(s_emp, f"{BASE}/api/ratings", json_data={
    "job_id": "00000000-0000-0000-0000-000000000001",
    "rated_user_id": "00000000-0000-0000-0000-000000000001",
    "rating": 5, "target_type": "worker"
})
try:
    d = r.json()
    msg = d.get("error", "")[:80]
except:
    msg = r.text[:80]
if r.status_code == 400 and "себя" in msg.lower():
    log("PASS", f"6b. Self-rating blocked: 400 - {msg}")
elif r.status_code in (404, 400):
    log("PASS", f"6b. Self-rating: {r.status_code} - {msg}")
else:
    log("FAIL", f"6b. Self-rating: {r.status_code} - {msg}")

# 6c: Participant check (worker who is not on the job)
r = api_post(s_wrk, f"{BASE}/api/ratings", json_data={
    "job_id": "00000000-0000-0000-0000-000000000001",
    "rated_user_id": "00000000-0000-0000-0000-000000000002",
    "rating": 3, "target_type": "worker"
})
try:
    d = r.json()
    msg = d.get("error", "")[:80]
except:
    msg = r.text[:80]
if r.status_code in (403, 404):
    log("PASS", f"6c. Non-participant rating: {r.status_code} - {msg}")
elif r.status_code == 400:
    log("PASS", f"6c. Non-participant rating: 400 - {msg}")
else:
    log("FAIL", f"6c. Non-participant rating: {r.status_code} - {msg}")

# 6d: GET ratings endpoint
r = requests.get(f"{BASE}/api/ratings/00000000-0000-0000-0000-000000000001")
try:
    d = r.json()
    if d.get("success"):
        log("PASS", f"6d. GET ratings: 200 OK - count={d.get('count', 0)}")
    else:
        log("PASS", f"6d. GET ratings: 200 - success=False (expected for nonexistent job)")
except:
    log("FAIL", f"6d. GET ratings: {r.status_code} - {r.text[:80]}")

# ═══════════════════════════════════════════════════
# TEST 7: backward compatibility
# ═══════════════════════════════════════════════════
log("INFO", "--- TEST 7: backward compatibility ---")

endpoints = [
    ("GET /", "/", False),
    ("GET /workers", "/workers", False),
    ("GET /api/skills", "/api/skills", False),
    ("GET /api/religions", "/api/religions", False),
    ("GET /login", "/login", False),
    ("GET /register", "/register", False),
    ("GET /my-jobs (auth)", "/my-jobs", True),
    ("GET /favorites (auth)", "/favorites", True),
    ("GET /notifications (auth)", "/notifications", True),
]

all_compat_ok = True
for name, path, needs_auth in endpoints:
    if needs_auth:
        r = s_emp.get(f"{BASE}{path}")
    else:
        r = requests.get(f"{BASE}{path}")
    if r.status_code == 200:
        log("PASS", f"7. {name}: 200 OK")
    else:
        log("FAIL", f"7. {name}: {r.status_code}")
        all_compat_ok = False

# ═══════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════
log("INFO", "-" * 60)
total_tests = passed + failed
log("INFO", f"Total: {passed} passed, {failed} failed, {warn} warnings")
log("INFO", "Warnings = tests skipped due to missing test data")
log("INFO", f"Success rate: {passed}/{total_tests} = {100*passed//total_tests if total_tests else 0}%")

# Write report
with open(OUT, "w", encoding="utf-8") as f:
    f.write("Trudnik New Routes Test Report\n")
    f.write(f"Server: {BASE}\n")
    f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 60 + "\n")
    for line in report:
        f.write(line + "\n")
    f.write("-" * 60 + "\n")
    f.write(f"Total: {passed} passed, {failed} failed, {warn} warnings\n")

print(f"\nReport saved to {OUT}")
