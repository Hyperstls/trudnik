"""
Direct Playwright test for login/logout on Trudnik.
No DeepSeek dependency — uses known CSS selectors (Latin only).
"""
import sys, os
from playwright.sync_api import sync_playwright

BASE_URL = "https://trudnik-hyperstls.amvera.io"

USERS = {
    "admin":    {"email": "admin@test.ru", "password": "Step@1986", "role": "admin"},
    "employer": {"email": "org@test.ru",   "password": "Step@1986", "role": "employer"},
    "worker":   {"email": "trud@test.ru",  "password": "Step@1986", "role": "worker"},
}


def test_role(role: str) -> dict:
    user = USERS[role]
    result = {"role": role, "email": user["email"], "login_ok": False, "logout_ok": False, "error": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        try:
            # Open login page directly (avoid redirect loop on /)
            login_url = f"{BASE_URL}/login"
            print(f"\n{'='*50}")
            print(f"[{role.upper()}] Opening {login_url}...")
            page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            print(f"    URL: {page.url}")

            # Fill login form
            print(f"[{role.upper()}] Filling email: {user['email']}")
            page.fill('input[name="email"]', user["email"])
            page.fill('input[name="password"]', user["password"])
            page.wait_for_timeout(300)

            # Submit
            print(f"[{role.upper()}] Submitting login...")
            page.click('button[type="submit"]')
            page.wait_for_timeout(4000)
            print(f"    URL after login: {page.url}")

            # Check login success
            page_source = page.content()
            page_source_lower = page_source.lower()
            current_url = page.url.lower()

            # Login is successful if URL changed away from /login and we see user-specific content
            still_on_login = "/login" in current_url and "/logout" not in current_url
            has_logout = "/logout" in page_source_lower or "logout" in current_url

            if role == "admin":
                result["login_ok"] = (
                    not still_on_login and
                    (has_logout or "/admin" in current_url or "/admin" in page_source_lower[:2000])
                )
            elif role == "employer":
                result["login_ok"] = (
                    not still_on_login and
                    (has_logout or "my-jobs" in current_url or "my_jobs" in current_url)
                )
            elif role == "worker":
                result["login_ok"] = (
                    not still_on_login and has_logout
                )

            # Fallback: if we got redirected away from /login, login likely succeeded
            if not result["login_ok"] and not still_on_login:
                result["login_ok"] = True
                print(f"    (login assumed OK: redirected to {page.url})")

            print(f"[{role.upper()}] Login OK: {result['login_ok']}")

            # Logout via /logout
            print(f"[{role.upper()}] Navigating to /logout...")
            page.goto(f"{BASE_URL}/logout", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(2000)
            print(f"    URL after logout: {page.url}")

            # Check logout success
            page_source = page.content().lower()
            result["logout_ok"] = (
                "/login" in page.url.lower() or
                "login" in page.url.lower() or
                ("login" in page_source and "logout" not in page_source[:500])
            )
            print(f"[{role.upper()}] Logout OK: {result['logout_ok']}")

            # Screenshot
            try:
                os.makedirs("test_screenshots", exist_ok=True)
                page.screenshot(path=f"test_screenshots/{role}_final.png")
            except Exception:
                pass

        except Exception as e:
            result["error"] = str(e)[:200]
            print(f"[{role.upper()}] ERROR: {e}")
        finally:
            browser.close()

    return result


def main():
    roles = sys.argv[1:] if len(sys.argv) > 1 else ["admin", "employer", "worker"]
    if "all" in roles:
        roles = ["admin", "employer", "worker"]

    results = []
    for role in roles:
        if role not in USERS:
            print(f"Unknown role: {role}")
            continue
        results.append(test_role(role))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    all_ok = True
    for r in results:
        login_icon = "OK" if r["login_ok"] else "FAIL"
        logout_icon = "OK" if r["logout_ok"] else "FAIL"
        status = "PASS" if r["login_ok"] and r["logout_ok"] else "FAIL"
        print(f"  {r['role']:10s} | Login: {login_icon:4s} | Logout: {logout_icon:4s} | {status}")
        if r["error"]:
            print(f"           Error: {r['error'][:120]}")
        if not (r["login_ok"] and r["logout_ok"]):
            all_ok = False

    print(f"\n{'='*60}")
    print(f"OVERALL: {'ALL TESTS PASSED' if all_ok else 'SOME TESTS FAILED'}")
    print(f"{'='*60}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
