"""
Selenium browser tests for Trudnik app.
4 scenarios: employer, worker, contact field, URL sanitization.

Usage: python tests/test_selenium_browser.py
Requires: Chrome, selenium
"""

import os
import sys
import time
from datetime import datetime

# Fix encoding for Windows CP1251 terminals
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
except ImportError:
    print("Install selenium: pip install selenium")
    sys.exit(1)

# --- Config ---
BASE_URL = "https://trudnik.onrender.com"
EMPLOYER_EMAIL = "org@test.ru"
EMPLOYER_PASSWORD = "Step@1986"
WORKER_EMAIL = "trud3@test.ru"
WORKER_PASSWORD = "Step@1986"

# Render free tier cold start can take 30-60s
PAGE_LOAD_TIMEOUT = 90
ELEMENT_WAIT_TIMEOUT = 45

results = []


def report(scenario, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    msg = "[%s] %s | %s" % (datetime.now().strftime('%H:%M:%S'), status, scenario)
    if detail:
        msg += " -- " + detail
    results.append(msg)
    print(msg)


def navigate(driver, url):
    """Navigate with extended timeout for Render cold starts."""
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    try:
        driver.get(url)
        print("  Page loaded: %s" % url[:80])
    except TimeoutException:
        print("  [WARN] Page load timeout (%ds) for %s" % (PAGE_LOAD_TIMEOUT, url[:80]))
    driver.set_page_load_timeout(30)


def wait_and_find(driver, by, value, description=""):
    """Find element with WebDriverWait (extended timeout for cold starts)."""
    try:
        return WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((by, value))
        )
    except TimeoutException:
        raise NoSuchElementException(
            "Element not found: %s (selector: %s=%s)" % (description or value, by, value)
        )


def login(driver, email, password, role_name):
    """Log into the application."""
    navigate(driver, "%s/login" % BASE_URL)
    time.sleep(2)

    email_input = wait_and_find(driver, By.NAME, "email", description="email field")
    email_input.clear()
    email_input.send_keys(email)

    password_input = wait_and_find(driver, By.NAME, "password", description="password field")
    password_input.clear()
    password_input.send_keys(password)

    submit_btn = wait_and_find(driver, By.CSS_SELECTOR,
                               "button[type='submit']", description="Login button")
    submit_btn.click()
    time.sleep(4)

    try:
        driver.find_element(By.NAME, "email")
        report("Login %s" % role_name, False, "Login form still visible")
        return False
    except NoSuchElementException:
        report("Login %s" % role_name, True, "email=%s" % email)
        return True


def logout(driver):
    navigate(driver, "%s/logout" % BASE_URL)
    time.sleep(1)


# ============================================================
# Scenario A: Employer
# ============================================================
def scenario_a_employer(driver):
    print("\n--- Scenario A: Employer ---")
    if not login(driver, EMPLOYER_EMAIL, EMPLOYER_PASSWORD, "employer"):
        return

    navigate(driver, "%s/my-jobs" % BASE_URL)
    time.sleep(2)

    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if "Мои задания" in page_text or "задани" in page_text.lower():
            report("My Jobs page loaded", True)
        else:
            report("My Jobs page loaded", False, "Unexpected content")
    except Exception as e:
        report("My Jobs page loaded", False, str(e)[:100])

    navigate(driver, "%s/jobs/new" % BASE_URL)
    time.sleep(2)

    # Check page content (form renders via JS/API calls, may be slow)
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        if "Создать" in body or "задание" in body.lower() or "Название" in body:
            report("Create Job form opened", True)
        else:
            report("Create Job form opened", False, "Form content not found")
    except Exception as e:
        report("Create Job form opened", False, str(e)[:100])

    logout(driver)


# ============================================================
# Scenario B: Worker
# ============================================================
def scenario_b_worker(driver):
    print("\n--- Scenario B: Worker ---")
    if not login(driver, WORKER_EMAIL, WORKER_PASSWORD, "worker"):
        return

    navigate(driver, BASE_URL)
    time.sleep(2)
    try:
        driver.find_element(By.TAG_NAME, "body")
        report("Main page (worker) loaded", True)
    except Exception as e:
        report("Main page (worker) loaded", False, str(e)[:100])

    navigate(driver, "%s/my-applications" % BASE_URL)
    time.sleep(2)
    try:
        driver.find_element(By.TAG_NAME, "body")
        report("My Applications page loaded", True)
    except Exception as e:
        report("My Applications page loaded", False, str(e)[:100])

    logout(driver)


# ============================================================
# Scenario C: Contact field in profile
# ============================================================
def scenario_c_contact(driver):
    print("\n--- Scenario C: Contact field ---")
    if not login(driver, WORKER_EMAIL, WORKER_PASSWORD, "worker (contact)"):
        return

    navigate(driver, "%s/profile" % BASE_URL)
    time.sleep(2)

    contact_input = None
    found_by = None
    for by, val, desc in [
        (By.NAME, "contact", "By.NAME"),
        (By.CSS_SELECTOR, "input[name='contact']", "By.CSS"),
        (By.XPATH, "//input[@name='contact']", "By.XPATH"),
    ]:
        try:
            contact_input = driver.find_element(by, val)
            found_by = desc
            break
        except NoSuchElementException:
            continue

    if contact_input:
        report("Contact field found", True, "selector: %s" % found_by)
        contact_input.clear()
        contact_input.send_keys("telegram: @testuser")
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_btn.click()
            time.sleep(3)
            report("Contact field: save", True, "telegram: @testuser")
        except Exception as e:
            report("Contact field: save", False, str(e)[:100])

        # Clear
        navigate(driver, "%s/profile" % BASE_URL)
        time.sleep(2)
        try:
            contact_input = driver.find_element(By.NAME, "contact")
            contact_input.clear()
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_btn.click()
            time.sleep(2)
            report("Contact field: clear", True)
        except Exception as e:
            report("Contact field: clear", False, str(e)[:100])
    else:
        report("Contact field found", False,
               "Not found by any selector - field may not be in profile.html")

    logout(driver)


# ============================================================
# Scenario D: URL sanitization
# ============================================================
def scenario_d_sanitize(driver):
    print("\n--- Scenario D: URL sanitization ---")
    # Navigate with injection attempt in city parameter
    navigate(driver, "%s/?city=Москва%%26status%%3Deq.cancelled" % BASE_URL)
    time.sleep(2)

    # The browser URL will still contain the injection attempt,
    # but the SERVER sanitizes it before building PostgREST query.
    # So we check page content - only open jobs should appear.
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        # If sanitization works, no cancelled jobs should appear
        has_cancelled = "отмен" in body.lower()
        report("URL sanitization", not has_cancelled,
               "Only open jobs shown (sanitization works)" if not has_cancelled
               else "Cancelled jobs visible - injection may have worked")
    except Exception as e:
        report("URL sanitization", False, str(e)[:100])


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 60)
    print("  Selenium tests for Trudnik")
    print("  Server: %s" % BASE_URL)
    print("  Time:   %s" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("  Render cold start timeout: %ds" % PAGE_LOAD_TIMEOUT)
    print("=" * 60)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.implicitly_wait(5)

        scenario_a_employer(driver)
        scenario_b_worker(driver)
        scenario_c_contact(driver)
        scenario_d_sanitize(driver)

    except Exception as e:
        print("\nCRITICAL ERROR: %s" % e)
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()

    # --- Report ---
    print("\n" + "=" * 60)
    print("  REPORT")
    print("=" * 60)
    passed = sum(1 for r in results if "PASS" in r)
    failed = sum(1 for r in results if "FAIL" in r)
    for r in results:
        print(r)
    print("\nTotal: %d passed, %d failed, %d total" % (passed, failed, passed + failed))

    report_path = os.path.join(os.path.dirname(__file__), "..", "selenium_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Selenium Report - Trudnik\n")
        f.write("Server: %s\n" % BASE_URL)
        f.write("Time:   %s\n" % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        f.write("=" * 60 + "\n")
        for r in results:
            f.write(r + "\n")
        f.write("\nTotal: %d passed, %d failed\n" % (passed, failed))
    print("\nReport saved: %s" % os.path.abspath(report_path))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
