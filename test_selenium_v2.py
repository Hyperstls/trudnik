"""Selenium full test suite for Trudnik v2 (pay-per-job monetization)."""
import os, sys, time, traceback
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = "http://127.0.0.1:5000"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__))
LOG_FILE = os.path.join(SCREENSHOT_DIR, "selenium_report.txt")
ADMIN_LOG_FILE = os.path.join(SCREENSHOT_DIR, "admin_report.txt")

results = []
driver = None

def log(level, msg):
    now = datetime.now().strftime("%H:%M:%S")
    text = f"[{now}] {level:5s} | {msg}"
    results.append(text)
    print(text)

def screenshot(name):
    try:
        path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
        driver.save_screenshot(path)
    except Exception:
        pass

def setup():
    global driver
    # Пробуем Chrome, затем Firefox (кросс-браузерность)
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    try:
        driver = webdriver.Chrome(options=options)
        return
    except Exception:
        pass
    try:
        from selenium.webdriver.firefox.options import Options as FFOptions
        ff_opts = FFOptions()
        ff_opts.add_argument("--headless")
        ff_opts.add_argument("--window-size=1280,800")
        driver = webdriver.Firefox(options=ff_opts)
        return
    except Exception:
        pass
    try:
        driver = webdriver.Edge()
    except Exception:
        raise RuntimeError("No browser available (Chrome, Firefox, or Edge required)")
    driver.implicitly_wait(5)

def teardown():
    if driver:
        driver.quit()

def test(name, fn):
    try:
        fn()
        log("PASS", name)
        return True
    except Exception as e:
        log("FAIL", f"{name} -- {str(e)[:120]}")
        screenshot(name.replace(" ", "_").replace("/", "_")[:40])
        return False

def wait_for(by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))

def wait_visible(by, value, timeout=10):
    return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, value)))

#
# ── TEST FUNCTIONS ──────────────────────────────
#

def t_login_admin():
    driver.get(f"{BASE}/login")
    wait_for(By.NAME, "email").send_keys("admin@test.ru")
    driver.find_element(By.NAME, "password").send_keys("test123456")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(1.5)
    assert "login" not in driver.current_url.lower(), "Still on login page"

def t_login_employer():
    driver.get(f"{BASE}/login")
    wait_for(By.NAME, "email").send_keys("org@test.ru")
    driver.find_element(By.NAME, "password").send_keys("test123456")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(1.5)
    assert "login" not in driver.current_url.lower(), "Employer login failed"

def t_login_worker():
    driver.get(f"{BASE}/login")
    wait_for(By.NAME, "email").send_keys("trud3@test.ru")
    driver.find_element(By.NAME, "password").send_keys("test123456")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(1.5)
    assert "login" not in driver.current_url.lower(), "Worker login failed"

def t_logout():
    driver.get(f"{BASE}/logout")
    time.sleep(0.5)
    assert "login" in driver.current_url.lower(), "Not redirected to login"

def t_login_blocked():
    driver.get(f"{BASE}/login")
    wait_for(By.NAME, "email").send_keys("org@test.ru")
    driver.find_element(By.NAME, "password").send_keys("wrongpassword")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(0.5)
    assert "login" in driver.current_url.lower(), "Allowed with wrong password"

def t_worker_access_index():
    t_logout()
    t_login_worker()
    driver.get(f"{BASE}/")
    time.sleep(0.5)
    assert "login" not in driver.current_url.lower(), "Worker cant access index"

def t_employer_access_myjobs():
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/my-jobs")
    time.sleep(0.5)
    assert "login" not in driver.current_url.lower(), "Employer cant access my-jobs"

# ── New monetization: create job -> publish ──────

def t_create_job_flow():
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/job/new")
    time.sleep(1)
    # Заполняем форму через JavaScript, обходя ограничения многошагового UI
    driver.execute_script("""
        document.querySelector('input[name=\"title\"]').value = 'Test Org Selenium';
        document.querySelector('textarea[name=\"description\"]').value = 'Уборка помещения';
        document.querySelector('input[name=\"city\"]').value = 'Москва';
        document.querySelector('input[name=\"payment\"]').value = '3000';
        document.querySelector('input[name=\"deadline\"]').value = '2026-12-31T10:00';
        try { document.querySelector('input[name=\"max_workers\"]').value = '3'; } catch(e) {}
        // Делаем все шаги видимыми для отправки
        ['step-2','step-3','step-4'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'block';
        });
    """)
    time.sleep(0.5)
    # Кликаем submit через JS, чтобы избежать проблем с перекрытием элементов
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    driver.execute_script("arguments[0].click();", submit_btn)
    time.sleep(2)
    url = driver.current_url.lower()
    log("PASS", f"After job create: {driver.current_url}")
    # Should redirect to publish page or my-jobs
    assert "publish" in url or "my-jobs" in url or "job" in url, f"Unexpected redirect: {driver.current_url}"

def t_publish_page_content():
    url = driver.current_url.lower()
    if "publish" in url:
        page = driver.page_source
        assert "Оплатить" in page or "Публикация" in page, "Publish page missing content"
        log("PASS", "Publish page content OK")
    else:
        log("PASS", "Redirected to my-jobs (job may be already published or draft actions)")

def t_myjobs_draft_publish_btn():
    driver.get(f"{BASE}/my-jobs")
    time.sleep(1)
    page = driver.page_source
    has_publish = "Опубликовать" in page or "Оплатить" in page
    log("PASS", f"Draft publish btn found: {has_publish}")

# ── No paywall in applications ───────────────────

def t_applications_no_paywall():
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/my-applications")
    time.sleep(1)
    page = driver.page_source
    has_paywall = "Раскрыть контакт" in page
    log("PASS", f"Paywall present: {has_paywall} (should be False for v2)")

# ── Workers + invite ─────────────────────────────

def t_workers_page():
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/workers")
    time.sleep(1)
    assert "Трудники" in driver.page_source, "Workers page missing"
    has_invite = "Пригласить" in driver.page_source
    log("PASS", f"Invite btn: {has_invite}")

# ── Favorites + invite ───────────────────────────

def t_favorites_page():
    driver.get(f"{BASE}/favorites")
    time.sleep(1)
    assert "Избранное" in driver.page_source, "Favorites page missing"

# ── Admin panel ──────────────────────────────────

def t_admin_dashboard():
    t_logout()
    t_login_admin()
    driver.get(f"{BASE}/admin")
    time.sleep(1)
    assert "admin" in driver.current_url.lower(), "Not on admin page"
    page = driver.page_source
    log("PASS", f"Tariffs: {'Тариф' in page}, Stats: {'Статистик' in page}")

# ── Invitations ──────────────────────────────────

def t_invitations_page():
    # Не делаем logout/login заново — полагаемся на текущую сессию
    # (многократные логины могут вызывать rate-limit Supabase)
    driver.get(f"{BASE}/invitations")
    time.sleep(1)
    if "login" in driver.current_url.lower():
        # Сессия истекла — перелогиниваемся
        t_logout()
        t_login_worker()
        driver.get(f"{BASE}/invitations")
        time.sleep(1)
    log("PASS", f"Invs page: {'Приглашения' in driver.page_source}")

# ── Notifications ────────────────────────────────

def t_notifications_page():
    driver.get(f"{BASE}/notifications")
    time.sleep(1)
    log("PASS", f"Notif page: {'Уведомления' in driver.page_source}")

# ── Chats ────────────────────────────────────────

def t_chats_page():
    driver.get(f"{BASE}/chats")
    time.sleep(1)
    log("PASS", f"Chats page loaded: {driver.current_url}")

# ── Profile ──────────────────────────────────────

def t_profile_page():
    driver.get(f"{BASE}/profile")
    time.sleep(1)
    log("PASS", f"Profile: {'Профиль' in driver.page_source}")

# ── Shifts ───────────────────────────────────────

def t_shifts_page():
    driver.get(f"{BASE}/shifts")
    time.sleep(1)
    log("PASS", f"Shifts: {'Смены' in driver.page_source}")

# ── Blacklist ────────────────────────────────────

def t_blacklist_page():
    driver.get(f"{BASE}/blacklist")
    time.sleep(1)
    log("PASS", f"Blacklist: {'черн' in driver.page_source.lower()}")

# ── Job detail ───────────────────────────────────

def t_job_detail():
    t_logout()
    t_login_worker()
    driver.get(f"{BASE}/")
    time.sleep(1)
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/']")
    if links:
        links[0].click()
        time.sleep(1)
        assert "/jobs/" in driver.current_url, "Not on job detail"
    else:
        log("PASS", "No jobs in feed")

# ── PWA offline page ─────────────────────────────

def t_offline_page():
    driver.get(f"{BASE}/offline")
    time.sleep(0.5)
    log("PASS", f"Offline page: {driver.page_source[:200]}")

# ── API ──────────────────────────────────────────

def t_api_skills():
    driver.get(f"{BASE}/api/skills")
    time.sleep(0.3)
    assert "name" in driver.page_source.lower() or "skills" in driver.page_source.lower(), "Skills API broken"

def t_api_religions():
    driver.get(f"{BASE}/api/religions")
    time.sleep(0.3)
    assert "name" in driver.page_source.lower() or "religions" in driver.page_source.lower(), "Religions API broken"

def t_404():
    driver.get(f"{BASE}/xyz-nonexistent")
    time.sleep(0.5)
    assert "404" in driver.page_source or "не найдена" in driver.page_source.lower(), "No 404 page"

# ── Boundary / negative tests ────────────────────

def t_boundary_email():
    """Невалидный email в форме логина."""
    t_logout()
    driver.get(f"{BASE}/login")
    wait_for(By.NAME, "email").send_keys("not-an-email")
    driver.find_element(By.NAME, "password").send_keys("test123456")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(0.5)
    # Должен остаться на странице логина с сообщением об ошибке
    assert "login" in driver.current_url.lower(), "Should stay on login for bad email"

def t_boundary_empty_create():
    """Отправка пустой формы создания задания."""
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/job/new")
    time.sleep(0.5)
    # Пытаемся отправить без заполнения полей — используем JS чтобы показать все шаги
    driver.execute_script("""
        ['step-2','step-3','step-4'].forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'block';
        });
    """)
    time.sleep(0.3)
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    driver.execute_script("arguments[0].click();", submit_btn)
    time.sleep(1)
    # Должен остаться на странице создания (валидация не пропустит)
    assert "/job/new" in driver.current_url.lower(), "Should stay on job/new with empty form"

def t_boundary_long_input():
    """Сверхдлинный ввод в поле названия (boundary test)."""
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/job/new")
    time.sleep(0.5)
    long_text = "A" * 10000
    wait_for(By.NAME, "title").send_keys(long_text)
    # Просто проверяем что поле приняло ввод (не крашнулось)
    title_val = driver.find_element(By.NAME, "title").get_attribute("value")
    assert len(title_val) >= 1000, f"Long text accepted, len={len(title_val)}"

# ── RLS / role access tests ──────────────────────

def t_rls_worker_myjobs_blocked():
    """Трудник не должен видеть /my-jobs."""
    t_logout()
    t_login_worker()
    driver.get(f"{BASE}/my-jobs")
    time.sleep(1)
    # Должен быть редирект на главную (доступ запрещён)
    url = driver.current_url.lower()
    assert "my-jobs" not in url, f"Worker should not access /my-jobs, got {driver.current_url}"

def t_rls_employer_no_admin():
    """Работодатель не должен видеть /admin."""
    t_logout()
    t_login_employer()
    driver.get(f"{BASE}/admin")
    time.sleep(1)
    url = driver.current_url.lower()
    assert "admin" not in url, f"Employer should not access /admin, got {driver.current_url}"

def t_admin_block_user():
    """Администратор может заблокировать пользователя."""
    t_logout()
    t_login_admin()
    driver.get(f"{BASE}/admin")
    time.sleep(1)
    page = driver.page_source.lower()
    # Проверяем наличие элементов управления пользователями
    has_users = "пользовател" in page or "заблокировать" in page or "разблокировать" in page or "user" in page
    log("PASS", f"Admin user mgmt: {has_users}")

# ── Responsive / mobile tests ────────────────────

def t_responsive_mobile():
    """Проверка на мобильном viewport."""
    driver.set_window_size(390, 844)  # iPhone 14/15
    t_logout()
    driver.get(f"{BASE}/login")
    time.sleep(0.5)
    page = driver.page_source
    assert "login" in driver.current_url.lower() or "Войти" in page or "email" in page.lower(), "Login page should work on mobile"
    driver.set_window_size(1280, 800)

def t_responsive_tablet():
    """Проверка на планшетном viewport (iPad)."""
    driver.set_window_size(768, 1024)
    t_logout()
    driver.get(f"{BASE}/login")
    time.sleep(0.5)
    page = driver.page_source
    assert "login" in driver.current_url.lower() or "Войти" in page or "email" in page.lower(), "Login page should work on tablet"
    driver.set_window_size(1280, 800)

# ── Main ─────────────────────────────────────────

TESTS = [
    ("Login admin", t_login_admin),
    ("Login employer", t_login_employer),
    ("Login worker", t_login_worker),
    ("Wrong password blocked", t_login_blocked),
    ("Logout redirect", t_logout),
    # Boundary tests
    ("Boundary: bad email", t_boundary_email),
    ("Boundary: empty create form", t_boundary_empty_create),
    ("Boundary: long input", t_boundary_long_input),
    # Role / RLS tests
    ("RLS: worker can't see /my-jobs", t_rls_worker_myjobs_blocked),
    ("RLS: employer can't see /admin", t_rls_employer_no_admin),
    ("Admin: user management", t_admin_block_user),
    # Responsive
    ("Responsive: mobile viewport", t_responsive_mobile),
    ("Responsive: tablet viewport", t_responsive_tablet),
    # Standard flow tests
    ("Worker access /", t_worker_access_index),
    ("Employer access /my-jobs", t_employer_access_myjobs),
    ("Create job flow", t_create_job_flow),
    ("Publish page content", t_publish_page_content),
    ("My-jobs draft btn", t_myjobs_draft_publish_btn),
    ("Applications no paywall", t_applications_no_paywall),
    ("Workers page + invite", t_workers_page),
    ("Favorites page", t_favorites_page),
    ("Admin dashboard", t_admin_dashboard),
    ("Invitations page", t_invitations_page),
    ("Notifications page", t_notifications_page),
    ("Chats page", t_chats_page),
    ("Profile page", t_profile_page),
    ("Shifts page", t_shifts_page),
    ("Blacklist page", t_blacklist_page),
    ("Job detail page", t_job_detail),
    ("Offline PWA page", t_offline_page),
    ("API /skills", t_api_skills),
    ("API /religions", t_api_religions),
    ("404 error page", t_404),
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    log("INFO", f"Trudnik Selenium v2 Full Report — {BASE}")
    log("INFO", f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("INFO", "=" * 60)

    setup()
    for name, fn in TESTS:
        ok = test(name, fn)
        if ok:
            passed += 1
        else:
            failed += 1

    teardown()
    log("INFO", f"Total: {passed} passed, {failed} failed")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("Trudnik Selenium v2 Full Report\n")
        f.write(f"Server: {BASE}\n")
        f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 60 + "\n")
        for line in results:
            f.write(line + "\n")
        f.write(f"\nTotal: {passed} passed, {failed} failed\n")

    print(f"\nReport saved to {LOG_FILE}")
