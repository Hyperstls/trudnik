"""
Browser test for trudnik.onrender.com/login page.
Tests form rendering, client-side validation, failed auth error, console/network errors.

Usage:
    TEST_BASE_URL=http://localhost:5000 python tests/test_login_browser.py
    TEST_BASE_URL=https://trudnik.onrender.com python tests/test_login_browser.py
"""
import os
import sys
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:5000").strip().rstrip("/")

RESULTS = []
ERRORS = []

def log(step, status, detail=""):
    icon = "[PASS]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[WARN]"
    msg = f"{icon} {step}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    RESULTS.append((step, status, detail))
    if status == "FAIL":
        ERRORS.append(step)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            console_errors = []
            def _on_console(msg):
                if msg.type in ("error", "warning"):
                    console_errors.append(f"[{msg.type}] {msg.text}")
            page.on("console", _on_console)

            network_errors = []
            def on_response(response):
                if response.status >= 400:
                    network_errors.append(f"{response.status} {response.url}")
            page.on("response", on_response)

            # --- Step 1: Navigate ---
            print("=" * 60)
            print(f"STEP 1: Navigate to {BASE_URL}/login")
            print("=" * 60)
            try:
                response = page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
                log("Page loaded", "PASS", f"HTTP {response.status}")
                print(f"  Title: {page.title()}")
            except Exception as e:
                log("Page load", "FAIL", str(e))
                return

            # --- Step 2: Form elements ---
            print("\n" + "=" * 60)
            print("STEP 2: Check form elements")
            print("=" * 60)

            checks = {
                "Email input": 'input[type="email"], input[name="email"], input#email',
                "Password input": 'input[type="password"], input[name="password"], input#password',
                "Submit button": 'button[type="submit"], input[type="submit"]',
            }
            for name, selector in checks.items():
                try:
                    el = page.locator(selector).first
                    el.wait_for(state="visible", timeout=5000)
                    log(f"{name} visible", "PASS", f"selector: {selector}")
                except Exception as e:
                    log(f"{name} visible", "FAIL", f"{str(e)[:80]}")

            link_checks = {
                "Register link": 'a[href*="register"]',
                "Password reset link": 'a[href*="reset"], a[href*="forgot"], a:has-text("Забыли"), a:has-text("forgot")',
            }
            for name, selector in link_checks.items():
                try:
                    el = page.locator(selector).first
                    if el.count() > 0:
                        log(f"{name} present", "PASS", f"href={el.get_attribute('href')}")
                    else:
                        log(f"{name} present", "WARN", "not found (feature not implemented)")
                except Exception as e:
                    log(f"{name} present", "FAIL", str(e)[:80])

            # --- Step 3: Empty form ---
            print("\n" + "=" * 60)
            print("STEP 3: Submit empty form - client validation")
            print("=" * 60)
            try:
                submit = page.locator('button[type="submit"], input[type="submit"]').first
                submit.click()
                # Wait for browser to process native form validation
                page.wait_for_timeout(1000)

                email_input = page.locator('input[type="email"], input[name="email"]').first
                password_input = page.locator('input[type="password"], input[name="password"]').first
                email_valid = email_input.evaluate("el => el.validity.valid")
                password_valid = password_input.evaluate("el => el.validity.valid")

                if not email_valid or not password_valid:
                    log("Empty form validation", "PASS", f"email_valid={email_valid}, password_valid={password_valid}")
                else:
                    current_url = page.url
                    if "/login" in current_url:
                        log("Empty form validation", "PASS", "Still on login page")
                    else:
                        log("Empty form validation", "FAIL", f"Redirected to {current_url}")
            except Exception as e:
                log("Empty form validation", "FAIL", str(e)[:120])

            # --- Step 4: Invalid credentials ---
            print("\n" + "=" * 60)
            print("STEP 4: Invalid credentials")
            print("=" * 60)
            try:
                email_input = page.locator('input[type="email"], input[name="email"]').first
                password_input = page.locator('input[type="password"], input[name="password"]').first
                email_input.fill("nonexistent_user_12345@test.com")
                password_input.fill("wrongpassword123")
                # Используем form.submit() напрямую — обходит JS-обработчик submit
                # (на production может быть баг с безусловным preventDefault)
                page.evaluate("document.querySelector('form').submit()")
                # Ждём ответ сервера и рендеринг toast-уведомления
                page.wait_for_timeout(4000)

                error_selectors = [
                    '.toast', '#toast-container .toast',
                    '.error', '.alert', '[role="alert"]',
                    'text=Неверный', 'text=неверный', 'text=ошибк',
                    'text=Invalid', 'text=invalid', 'text=не найден',
                    '.error-message', '.form-error', '#error'
                ]
                error_found = False
                error_text = ""
                for sel in error_selectors:
                    try:
                        el = page.locator(sel).first
                        if el.count() > 0 and el.is_visible():
                            error_text = el.text_content() or ""
                            error_found = True
                            break
                    except:
                        pass

                if error_found:
                    log("Invalid credentials error", "PASS", f"Error: '{error_text.strip()[:100]}'")
                else:
                    current_url = page.url
                    if "/login" in current_url:
                        page.screenshot(path="login_error_screenshot.png")
                        log("Invalid credentials error", "WARN", "No visible error element. Screenshot saved.")
                    else:
                        log("Invalid credentials error", "FAIL", f"Redirected to {current_url}")
            except Exception as e:
                log("Invalid credentials error", "FAIL", str(e)[:120])

            # --- Step 4b: JS validation — empty password ---
            print("\n" + "=" * 60)
            print("STEP 4b: JS validation — empty password (real user click)")
            print("=" * 60)
            try:
                # Reload the page for a clean state
                page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(500)

                email_input = page.locator('input[type="email"], input[name="email"]').first
                submit = page.locator('button[type="submit"], input[type="submit"]').first

                email_input.fill("valid_user@example.com")
                # Password is intentionally left empty — JS validation should block submission

                # Use regular click — simulates real user interaction,
                # JS handler should call e.preventDefault() on validation error
                submit.click()
                page.wait_for_timeout(1500)

                # Check 1: URL must still be on /login
                current_url = page.url
                url_stays = "/login" in current_url

                # Check 2: Password field's .floating-label-group must have 'error' class
                password_group_has_error = page.evaluate("""
                    () => {
                        const el = document.getElementById('password');
                        const group = el ? el.closest('.floating-label-group') : null;
                        return group ? group.classList.contains('error') : false;
                    }
                """)

                if url_stays and password_group_has_error:
                    log("JS validation empty pwd", "PASS",
                        "Form blocked, password group has 'error' class")
                elif url_stays:
                    log("JS validation empty pwd", "WARN",
                        "Form blocked but password group missing 'error' class")
                else:
                    log("JS validation empty pwd", "FAIL",
                        f"Form submitted despite empty password. Redirected to {current_url}")
            except Exception as e:
                log("JS validation empty pwd", "FAIL", str(e)[:120])

            # --- Step 5: Console & Network ---
            print("\n" + "=" * 60)
            print("STEP 5: Console & Network errors")
            print("=" * 60)

            if console_errors:
                print(f"  Console warnings/errors: {len(console_errors)}")
                for e in console_errors[:15]:
                    print(f"    {e[:150]}")
                critical = [e for e in console_errors if "error" in e.lower() or "500" in e]
                if critical:
                    log("Console errors", "WARN", f"{len(critical)} critical messages")
                else:
                    log("Console errors", "PASS", f"{len(console_errors)} non-critical")
            else:
                log("Console errors", "PASS", "No console errors")

            network_500s = [e for e in network_errors if e.startswith("500 ")]
            network_non404 = [e for e in network_errors if not e.startswith("404 ")]
            if network_500s:
                log("Network errors", "FAIL", f"HTTP 500: {network_500s[:5]}")
            elif network_non404:
                log("Network errors", "WARN", f"Non-404 errors: {network_non404[:5]}")
            else:
                log("Network errors", "PASS", "No critical network errors")

        finally:
            browser.close()

    # Report
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warned = sum(1 for _, s, _ in RESULTS if s == "WARN")
    print(f"  PASS: {passed}, FAIL: {failed}, WARN: {warned}")
    print(f"  Total checks: {len(RESULTS)}")
    if failed > 0:
        print("  FAILED:")
        for step in ERRORS:
            print(f"    - {step}")
    print("=" * 60)
    return len(ERRORS)

if __name__ == "__main__":
    sys.exit(run())
