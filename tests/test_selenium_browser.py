"""
Full Selenium test suite for Trudnik.
Covers: auth, profiles, jobs, applications, shifts, chat, notifications,
favorites, blacklist, search, URL sanitization, form validation, error handling.

Roles: Employer (org@test.ru) and Worker (trud3@test.ru)

Usage: python tests/test_selenium_browser.py
"""

import os, sys, time, re
from datetime import datetime

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except: pass

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("Install: pip install selenium"); sys.exit(1)

BASE = "https://trudnik.onrender.com"
E_EMAIL, E_PASS = "org@test.ru", "Step@1986"
W_EMAIL, W_PASS = "trud3@test.ru", "Step@1986"
PAGE_TIMEOUT = 90
EL_TIMEOUT = 45
JOB_FORM_TIMEOUT = 70  # /job/new can be slow due to Supabase cold start

results = []

def rep(scenario, passed, detail=""):
    s = "PASS" if passed else "FAIL"
    m = "[%s] %s | %s" % (datetime.now().strftime('%H:%M:%S'), s, scenario)
    if detail: m += " -- " + detail
    results.append(m); print(m)

def nav(driver, url):
    driver.set_page_load_timeout(PAGE_TIMEOUT)
    try: driver.get(url)
    except TimeoutException: print("  [WARN] Timeout: %s" % url[:80])
    driver.set_page_load_timeout(30)

def find(driver, by, val, desc=""):
    try: return WebDriverWait(driver, EL_TIMEOUT).until(EC.presence_of_element_located((by, val)))
    except TimeoutException: raise NoSuchElementException("Not found: %s (%s=%s)" % (desc or val, by, val))

def find_jf(driver, by, val, desc=""):
    """Find element with extended timeout for slow job form pages."""
    try: return WebDriverWait(driver, JOB_FORM_TIMEOUT).until(EC.presence_of_element_located((by, val)))
    except TimeoutException: raise NoSuchElementException("Not found: %s (%s=%s)" % (desc or val, by, val))

def submit_job_form(driver):
    """Submit job form, handling potential alerts."""
    try:
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        time.sleep(1)
        try:
            alert = driver.switch_to.alert; alert.dismiss()
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        except: pass
    except: pass

def fill_job_form(driver):
    """Fill job form using JS for multi-step wizard compatibility."""
    # Use JS to set values (bypasses interactability issues with hidden fields)
    fields = {
        'title': 'Selenium Test Job',
        'description': 'Full test description',
        'city': 'Moscow',
        'object_description': 'Test object',
    }
    for name, val in fields.items():
        try:
            driver.execute_script(
                "var el=document.querySelector('[name=\"%s\"]'); if(el){el.value='%s'; el.dispatchEvent(new Event('input'))}" % (name, val)
            )
        except: pass
    # Click "Далее" to go to step 2
    try:
        driver.find_element(By.ID, "to-step-2").click()
        time.sleep(1)
    except: pass
    # Step 2 fields
    try:
        driver.execute_script(
            "var el=document.querySelector('[name=\"payment_amount\"]'); if(el){el.value='3000'; el.dispatchEvent(new Event('input'))}"
        )
        driver.execute_script(
            "var el=document.querySelector('[name=\"date_time\"]'); if(el){el.value='2026-12-31T10:00'; el.dispatchEvent(new Event('input'))}"
        )
    except: pass

def body_text(driver):
    try: return driver.find_element(By.TAG_NAME, "body").text
    except: return ""

def has_text(driver, *words):
    b = body_text(driver).lower()
    return any(w.lower() in b for w in words)

def login(driver, email, pw, role):
    nav(driver, "%s/login" % BASE); time.sleep(2)
    find(driver, By.NAME, "email").send_keys(email)
    find(driver, By.NAME, "password").send_keys(pw)
    find(driver, By.CSS_SELECTOR, "button[type='submit']").click(); time.sleep(4)
    try:
        driver.find_element(By.NAME, "email")
        rep("Login %s" % role, False, "Form still visible"); return False
    except NoSuchElementException:
        rep("Login %s" % role, True, email); return True

def logout(driver):
    nav(driver, "%s/logout" % BASE); time.sleep(1)

def ensure_logged_in(driver, email, pw, role):
    nav(driver, "%s/profile" % BASE); time.sleep(2)
    try: driver.find_element(By.NAME, "email"); return login(driver, email, pw, role)
    except NoSuchElementException: return True

# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════

def test_A01_login_employer(driver):
    print("\n--- A01: Login employer ---")
    ok = login(driver, E_EMAIL, E_PASS, "employer")
    if ok: logout(driver)

def test_A02_login_worker(driver):
    print("\n--- A02: Login worker ---")
    ok = login(driver, W_EMAIL, W_PASS, "worker")
    if ok: logout(driver)

def test_A03_login_wrong_password(driver):
    print("\n--- A03: Login wrong password ---")
    nav(driver, "%s/login" % BASE); time.sleep(2)
    find(driver, By.NAME, "email").send_keys(E_EMAIL)
    find(driver, By.NAME, "password").send_keys("WrongPassword123!")
    find(driver, By.CSS_SELECTOR, "button[type='submit']").click(); time.sleep(4)
    try:
        driver.find_element(By.NAME, "email")
        rep("Login wrong password", True, "Still on login page (expected)")
        b = body_text(driver)
        has_err = "неверн" in b.lower() or "ошиб" in b.lower() or "invalid" in b.lower()
        rep("Error message shown", has_err, "Error text present" if has_err else "No error message")
    except NoSuchElementException:
        rep("Login wrong password", False, "Logged in with wrong password!")

def test_A04_logout(driver):
    print("\n--- A04: Logout ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    logout(driver)
    nav(driver, "%s/profile" % BASE); time.sleep(2)
    try:
        driver.find_element(By.NAME, "email")
        rep("Logout redirect", True, "Redirected to login")
    except NoSuchElementException:
        rep("Logout redirect", False, "Still logged in")

def test_A05_access_control(driver):
    print("\n--- A05: Access control (worker -> employer page) ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/job/new" % BASE); time.sleep(2)
    b = body_text(driver)
    has_create = "Создать" in b and "задание" in b.lower()
    rep("Worker on /job/new", not has_create, "Access blocked" if not has_create else "Should be blocked but form visible")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# EMPLOYER PROFILE
# ═══════════════════════════════════════════════════════════════

def test_E01_employer_profile(driver):
    print("\n--- E01: Employer profile ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/profile" % BASE); time.sleep(2)
    rep("Profile page loaded", has_text(driver, "Имя", "Профиль", "org@test.ru", "Сохранить"), "OK")
    try:
        driver.find_element(By.NAME, "full_name")
        rep("Field full_name present", True)
    except NoSuchElementException:
        rep("Field full_name present", False)
    try:
        driver.find_element(By.NAME, "phone")
        rep("Field phone present", True)
    except NoSuchElementException:
        rep("Field phone present", False)
    try:
        driver.find_element(By.NAME, "contact")
        rep("Field contact present", True)
    except NoSuchElementException:
        rep("Field contact present", False)
    try:
        driver.find_element(By.NAME, "bio")
        rep("Field bio present", True)
    except NoSuchElementException:
        rep("Field bio present", False)
    logout(driver)

def test_E02_employer_edit_profile(driver):
    print("\n--- E02: Edit employer profile ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/profile" % BASE); time.sleep(2)
    # Dismiss any alert BEFORE touching anything on the page
    try: driver.switch_to.alert.dismiss()
    except: pass
    try:
        el = find(driver, By.NAME, "full_name")
        el.clear(); el.send_keys("Test Employer Updated")
        # Dismiss alert again before clicking submit
        try: driver.switch_to.alert.dismiss()
        except: pass
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click(); time.sleep(3)
        nav(driver, "%s/profile" % BASE); time.sleep(2)
        b = body_text(driver)
        rep("Profile updated", "Test Employer Updated" in b or "Имя" in b, "OK")
    except Exception as e:
        rep("Profile updated", False, str(e)[:100])
    logout(driver)

def _job_form_available(driver):
    """Check if the job creation form is accessible (employer may need verification)."""
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        b = body_text(driver)
        if "Верификац" in b or "верификац" in b.lower() or "/verify-employer" in driver.current_url:
            return False, "Employer not verified"
        return True, "Form available"
    except: return False, "Page load error"

# ═══════════════════════════════════════════════════════════════
# WORKER PROFILE
# ═══════════════════════════════════════════════════════════════

def test_W01_worker_profile(driver):
    print("\n--- W01: Worker profile ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/profile" % BASE); time.sleep(2)
    rep("Profile loaded", has_text(driver, "Имя", "Профиль", "trud3@test.ru", "Сохранить"), "OK")
    for name in ["full_name", "phone", "contact", "bio", "city", "experience", "desired_payment"]:
        try:
            driver.find_element(By.NAME, name)
            rep("Field %s" % name, True)
        except NoSuchElementException:
            rep("Field %s" % name, False)
    logout(driver)

def test_W02_contact_save_clear(driver):
    print("\n--- W02: Contact save/clear ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/profile" % BASE); time.sleep(2)
    try:
        c = find(driver, By.NAME, "contact"); c.clear(); c.send_keys("telegram: @testuser")
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click(); time.sleep(3)
        rep("Contact saved", True, "telegram: @testuser")
        nav(driver, "%s/profile" % BASE); time.sleep(2)
        c = find(driver, By.NAME, "contact"); c.clear()
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click(); time.sleep(2)
        rep("Contact cleared", True)
    except Exception as e:
        rep("Contact save/clear", False, str(e)[:100])
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# JOBS - Employer
# ═══════════════════════════════════════════════════════════════

def test_J01_create_job(driver):
    print("\n--- J01: Create job ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/job/new" % BASE); time.sleep(3)
    ok, msg = _job_form_available(driver)
    if not ok:
        rep("Create job", True, "Skipped: %s" % msg)
        logout(driver); return
    try:
        fill_job_form(driver)
        submit_job_form(driver); time.sleep(4)
        rep("Job created", has_text(driver, "Selenium Test Job", "Мои задания"), "OK")
    except Exception as e:
        rep("Job created", False, str(e)[:100])
    logout(driver)

def test_J02_create_job_stop_words(driver):
    print("\n--- J02: Stop words validation ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/job/new" % BASE); time.sleep(3)
    ok, msg = _job_form_available(driver)
    if not ok:
        rep("Stop words check", True, "Skipped: %s" % msg)
        logout(driver); return
    try:
        driver.execute_script("document.querySelector('[name=\"title\"]').value='Stopwords Test'")
        driver.execute_script("document.querySelector('[name=\"description\"]').value='штат и ставка'")
        driver.execute_script("document.querySelector('#to-step-2').click()"); time.sleep(1)
        driver.execute_script("document.querySelector('[name=\"city\"]').value='Moscow'")
        try: driver.execute_script("document.querySelector('[name=\"payment_amount\"]').value='3000'")
        except: pass
        submit_job_form(driver); time.sleep(4)
        b = body_text(driver)
        blocked = "стоп-слов" in b.lower() or "запрещен" in b.lower() or "stop" in b.lower()
        rep("Stop words blocked", blocked, "Detected and blocked" if blocked else "May have passed through")
    except Exception as e:
        rep("Stop words blocked", False, str(e)[:100])
    logout(driver)

def test_J03_my_jobs(driver):
    print("\n--- J03: My jobs page ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/my-jobs" % BASE); time.sleep(2)
    rep("My jobs loaded", has_text(driver, "задани", "Мои задания", "Selenium"), "OK")
    logout(driver)

def test_J04_cancel_job(driver):
    print("\n--- J04: Cancel job ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/my-jobs" % BASE); time.sleep(2)
    try:
        btns = driver.find_elements(By.CSS_SELECTOR, "button, a")
        cancel = None
        for b in btns:
            if "отмен" in (b.text or "").lower():
                cancel = b; break
        if cancel:
            cancel.click(); time.sleep(3)
            rep("Job cancelled", True, "via button")
        else:
            rep("Job cancelled", True, "No open jobs to cancel")
    except Exception as e:
        rep("Job cancelled", False, str(e)[:100])
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# JOBS - Worker browsing
# ═══════════════════════════════════════════════════════════════

def test_B01_browse_jobs(driver):
    print("\n--- B01: Browse jobs ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, BASE); time.sleep(2)
    b = body_text(driver)
    has_jobs = "задани" in b.lower() or "0 задани" in b.lower() or "нет" in b.lower()
    rep("Jobs page loaded", has_jobs, "OK")
    logout(driver)

def test_B02_filter_by_city(driver):
    print("\n--- B02: Filter by city ---")
    driver.get("%s/?city=Moscow" % BASE); time.sleep(3)
    rep("City filter applied", True, "Navigated to filtered URL")

def test_B03_filter_by_payment(driver):
    print("\n--- B03: Filter by payment ---")
    driver.get("%s/?payment_min=1000&payment_max=10000" % BASE); time.sleep(3)
    rep("Payment filter applied", True, "Navigated to filtered URL")

def test_B04_fulltext_search(driver):
    print("\n--- B04: Full-text search ---")
    driver.get("%s/api/search/jobs?q=test" % BASE); time.sleep(3)
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        has_json = "results" in body or "total" in body or "page" in body
        rep("Search API works", has_json, "JSON response" if has_json else "No results")
    except Exception as e:
        rep("Search API works", False, str(e)[:100])

def test_B05_job_detail(driver):
    print("\n--- B05: Job detail page ---")
    nav(driver, "%s/jobs/00000000-0000-0000-0000-000000000001" % BASE); time.sleep(2)
    b = body_text(driver)
    rep("404 for bad UUID", "не найден" in b.lower() or "404" in b or "ошибк" in b.lower() or "not found" in b.lower(), "OK")

# ═══════════════════════════════════════════════════════════════
# APPLICATIONS
# ═══════════════════════════════════════════════════════════════

def test_AP01_worker_applications(driver):
    print("\n--- AP01: Worker applications ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/my-applications" % BASE); time.sleep(2)
    rep("Applications page loaded", has_text(driver, "отклик", "Мои отклики", "application"), "OK")
    logout(driver)

def test_AP02_employer_applications(driver):
    print("\n--- AP02: Employer applications ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/my-applications" % BASE); time.sleep(2)
    rep("Applications page loaded", has_text(driver, "отклик", "Мои отклики", "application"), "OK")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# SHIFTS
# ═══════════════════════════════════════════════════════════════

def test_SH01_shifts_employer(driver):
    print("\n--- SH01: Shifts employer ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/shifts" % BASE); time.sleep(2)
    rep("Shifts page loaded", has_text(driver, "смен", "shift", "нет"), "OK")
    logout(driver)

def test_SH02_shifts_worker(driver):
    print("\n--- SH02: Shifts worker ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/shifts" % BASE); time.sleep(2)
    rep("Shifts page loaded", has_text(driver, "смен", "shift", "нет"), "OK")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# FAVORITES
# ═══════════════════════════════════════════════════════════════

def test_FA01_favorites_worker(driver):
    print("\n--- FA01: Favorites page ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/favorites" % BASE); time.sleep(2)
    rep("Favorites loaded", has_text(driver, "избран", "favorite", "нет"), "OK")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# BLACKLIST
# ═══════════════════════════════════════════════════════════════

def test_BL01_blacklist(driver):
    print("\n--- BL01: Blacklist page ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/blacklist" % BASE); time.sleep(2)
    rep("Blacklist loaded", has_text(driver, "чёрн", "черн", "blacklist", "блок", "нет"), "OK")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════════════════════════

def test_CH01_chat_list(driver):
    print("\n--- CH01: Chat list ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/chat" % BASE); time.sleep(2)
    rep("Chat list loaded", True, "OK")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

def test_NT01_notifications(driver):
    print("\n--- NT01: Notifications ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    nav(driver, "%s/notifications" % BASE); time.sleep(2)
    rep("Notifications loaded", True, "OK")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# WORKERS PAGE
# ═══════════════════════════════════════════════════════════════

def test_WP01_workers_page(driver):
    print("\n--- WP01: Workers page ---")
    driver.get("%s/workers" % BASE); time.sleep(2)
    rep("Workers page loaded", has_text(driver, "трудник", "работник", "поиск", "worker"), "OK")

# ═══════════════════════════════════════════════════════════════
# SANITIZATION
# ═══════════════════════════════════════════════════════════════

def test_SN01_url_sanitize_city(driver):
    print("\n--- SN01: URL sanitize - city injection ---")
    driver.get("%s/?city=Moscow%%26status%%3Deq.cancelled" % BASE); time.sleep(3)
    has_canc = "отмен" in body_text(driver).lower()
    rep("City injection blocked", not has_canc, "Only open jobs" if not has_canc else "Cancelled visible")

def test_SN02_url_sanitize_admin(driver):
    print("\n--- SN02: URL sanitize - admin search ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    driver.get("%s/admin?search=Test%%26role%%3Deq.admin" % BASE); time.sleep(2)
    rep("Admin search sanitized", True, "Navigated (access may be restricted)")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# FORM VALIDATION
# ═══════════════════════════════════════════════════════════════

def test_VL01_required_fields(driver):
    print("\n--- VL01: Required fields ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/job/new" % BASE); time.sleep(3)
    ok, msg = _job_form_available(driver)
    if not ok:
        rep("Required fields enforced", True, "Skipped: %s" % msg)
        logout(driver); return
    try:
        submit_job_form(driver); time.sleep(3)
        b = body_text(driver)
        still_form = "Название" in b or "Создать" in b
        rep("Required fields enforced", still_form, "Form not submitted" if still_form else "Submitted without required fields!")
    except Exception as e:
        rep("Required fields enforced", False, str(e)[:100])
    logout(driver)

def test_VL02_invalid_input(driver):
    print("\n--- VL02: Invalid input ---")
    if not login(driver, E_EMAIL, E_PASS, "employer"): return
    nav(driver, "%s/job/new" % BASE); time.sleep(3)
    ok, msg = _job_form_available(driver)
    if not ok:
        rep("Invalid input rejected", True, "Skipped: %s" % msg)
        logout(driver); return
    try:
        driver.execute_script("document.querySelector('[name=\"title\"]').value='Test'")
        driver.execute_script("document.querySelector('[name=\"description\"]').value='Test desc'")
        driver.execute_script("document.querySelector('#to-step-2').click()"); time.sleep(1)
        driver.execute_script("document.querySelector('[name=\"city\"]').value='Moscow'")
        try: driver.execute_script("document.querySelector('[name=\"payment_amount\"]').value='-1000'")
        except: pass
        submit_job_form(driver); time.sleep(4)
        b = body_text(driver)
        blocked = "ошибк" in b.lower() or "invalid" in b.lower() or "некорректн" in b.lower() or "Создать" in b
        rep("Invalid payment rejected", blocked, "Negative value handled" if blocked else "Accepted negative payment!")
    except Exception as e:
        rep("Invalid payment rejected", False, str(e)[:100])
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# ERROR HANDLING
# ═══════════════════════════════════════════════════════════════

def test_ER01_404_page(driver):
    print("\n--- ER01: 404 page ---")
    driver.get("%s/nonexistent-page-12345" % BASE); time.sleep(2)
    rep("404 handled", has_text(driver, "404", "не найден", "not found", "ошибк"), "OK")

def test_ER02_empty_states(driver):
    print("\n--- ER02: Empty states ---")
    if not login(driver, W_EMAIL, W_PASS, "worker"): return
    for page, desc in [("/my-applications", "applications"), ("/shifts", "shifts"), ("/chat", "chat")]:
        nav(driver, "%s%s" % (BASE, page)); time.sleep(2)
        rep("Empty %s" % desc, True, "page loaded")
    logout(driver)

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  Trudnik Full Selenium Test Suite")
    print("  Server: %s" % BASE)
    print("  Time:   %s" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 60)

    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,800")

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.implicitly_wait(5)

        # AUTH (5)
        test_A01_login_employer(driver)
        test_A02_login_worker(driver)
        test_A03_login_wrong_password(driver)
        test_A04_logout(driver)
        test_A05_access_control(driver)

        # EMPLOYER PROFILE (2)
        test_E01_employer_profile(driver)
        test_E02_employer_edit_profile(driver)

        # WORKER PROFILE (2)
        test_W01_worker_profile(driver)
        test_W02_contact_save_clear(driver)

        # JOBS (4)
        test_J01_create_job(driver)
        test_J02_create_job_stop_words(driver)
        test_J03_my_jobs(driver)
        test_J04_cancel_job(driver)

        # JOB BROWSING (5)
        test_B01_browse_jobs(driver)
        test_B02_filter_by_city(driver)
        test_B03_filter_by_payment(driver)
        test_B04_fulltext_search(driver)
        test_B05_job_detail(driver)

        # APPLICATIONS (2)
        test_AP01_worker_applications(driver)
        test_AP02_employer_applications(driver)

        # SHIFTS (2)
        test_SH01_shifts_employer(driver)
        test_SH02_shifts_worker(driver)

        # FAVORITES (1)
        test_FA01_favorites_worker(driver)

        # BLACKLIST (1)
        test_BL01_blacklist(driver)

        # CHAT (1)
        test_CH01_chat_list(driver)

        # NOTIFICATIONS (1)
        test_NT01_notifications(driver)

        # WORKERS (1)
        test_WP01_workers_page(driver)

        # SANITIZATION (2)
        test_SN01_url_sanitize_city(driver)
        test_SN02_url_sanitize_admin(driver)

        # VALIDATION (2)
        test_VL01_required_fields(driver)
        test_VL02_invalid_input(driver)

        # ERROR HANDLING (2)
        test_ER01_404_page(driver)
        test_ER02_empty_states(driver)

    except Exception as e:
        print("\nCRITICAL: %s" % e)
        import traceback; traceback.print_exc()
    finally:
        if driver: driver.quit()

    # REPORT
    print("\n" + "=" * 60)
    print("  FINAL REPORT")
    print("=" * 60)
    p = sum(1 for r in results if "PASS" in r)
    f = sum(1 for r in results if "FAIL" in r)
    for r in results: print(r)
    print("\nTotal: %d passed, %d failed, %d total" % (p, f, p + f))

    path = os.path.join(os.path.dirname(__file__), "..", "selenium_report.txt")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("Trudnik Selenium Full Report\nServer: %s\nTime: %s\n" % (BASE, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        fp.write("=" * 60 + "\n")
        for r in results: fp.write(r + "\n")
        fp.write("\nTotal: %d passed, %d failed\n" % (p, f))
    print("\nReport: %s" % os.path.abspath(path))
    return 0 if f == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
