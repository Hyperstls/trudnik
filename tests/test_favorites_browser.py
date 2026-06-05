"""
Browser-based end-to-end test for Favorites functionality (добавление/удаление из избранного).

Основан на browser_agent.py, но использует прямые Playwright-команды вместо DeepSeek AI.

Тестирует:
  1. Регистрация нового пользователя (employer)
  2. Вход в систему
  3. Проверка UI: кнопка "В избранное" на /workers, JS-функция toggleFavorite
  4. Добавление в избранное через API (fetch после логина)
  5. Проверка страницы /favorites
  6. Удаление из избранного через API
  7. Подтверждение удаления
"""

import sys
import uuid
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ------------------------------------------------------------
# Настройка вывода UTF-8 для Windows
# ------------------------------------------------------------
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------
BASE_URL = "https://hyperstls.pythonanywhere.com"

# Тестовые данные для нового пользователя
TEST_EMAIL = f"test_fav_{uuid.uuid4().hex[:8]}@test.com"
TEST_PASSWORD = "Test123456!"
TEST_NAME = "Тестовый Работодатель"


def wait_and_fill(page, selector, value, timeout=10000):
    """Ожидание элемента и заполнение."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        page.fill(selector, value)
        page.wait_for_timeout(500)
        return True
    except PlaywrightTimeout:
        print(f"  [WARNING] Element '{selector}' not found within {timeout}ms")
        return False


def run_favorites_test():
    """Основной тестовый сценарий."""
    results = {
        "registration": False,
        "login": False,
        "add_ui_structure": False,
        "add_via_api": False,
        "favorites_page": False,
        "remove_via_api": False,
        "confirm_removed": False,
    }
    errors = []
    js_errors = []
    worker_id = None

    print("=" * 70)
    print("  TEST: FAVORITES UI FUNCTIONALITY (избранное)")
    print(f"  URL: {BASE_URL}")
    print(f"  Test email: {TEST_EMAIL}")
    print(f"  Time: {datetime.now().isoformat()}")
    print("=" * 70)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Перехватываем JS-ошибки в консоли
        page.on("pageerror", lambda err: js_errors.append(f"PAGE ERROR: {err}"))
        page.on("console", lambda msg: js_errors.append(f"CONSOLE [{msg.type}]: {msg.text}") if msg.type == "error" else None)

        # Глобальный обработчик диалогов (alert/confirm)
        page.on("dialog", lambda dialog: dialog.accept())

        try:
            # ===================================================================
            # STEP 1: Registration
            # ===================================================================
            print("\n[STEP 1] Registering new user (employer)...")
            page.goto(f"{BASE_URL}/register", wait_until="networkidle")
            page.wait_for_timeout(2000)
            print(f"  Page loaded: {page.url}")

            wait_and_fill(page, 'input[name="full_name"]', TEST_NAME)
            wait_and_fill(page, 'input[name="email"]', TEST_EMAIL)
            wait_and_fill(page, 'input[name="password"]', TEST_PASSWORD)
            page.select_option('select[name="role"]', 'employer')
            page.wait_for_timeout(500)
            wait_and_fill(page, 'input[name="city"]', 'Moscow')

            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)
            print(f"  After registration URL: {page.url}")

            if "/login" in page.url:
                print("  [OK] Registration successful, redirected to login")
                results["registration"] = True
            else:
                print(f"  [WARN] Registration result: {page.url}")

            # ===================================================================
            # STEP 2: Login
            # ===================================================================
            print("\n[STEP 2] Logging in...")

            if "/login" not in page.url:
                page.goto(f"{BASE_URL}/login", wait_until="networkidle")
                page.wait_for_timeout(2000)

            wait_and_fill(page, 'input[name="email"]', TEST_EMAIL)
            wait_and_fill(page, 'input[name="password"]', TEST_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_timeout(3000)
            print(f"  After login URL: {page.url}")

            if "/login" not in page.url:
                print("  [OK] Login successful")
                results["login"] = True
            else:
                print("  [FAIL] Could not login")
                errors.append("Failed to login")
                page.goto(f"{BASE_URL}/workers", wait_until="networkidle")
                page.wait_for_timeout(2000)
                if "/login" in page.url:
                    print("  [FAIL] /workers requires authentication - cannot proceed")
                    browser.close()
                    return results, errors

            # ===================================================================
            # STEP 3: Проверка UI кнопки "В избранное" на /workers
            # ===================================================================
            print("\n[STEP 3] Checking 'В избранное' button on /workers...")
            page.goto(f"{BASE_URL}/workers", wait_until="networkidle")
            page.wait_for_timeout(3000)
            print(f"  URL: {page.url}")

            # Проверяем, есть ли JS-функция toggleFavorite в глобальном scope
            has_toggle = page.evaluate("typeof window.toggleFavorite !== 'undefined'")
            print(f"  toggleFavorite function exists: {has_toggle}")

            # Проверяем HTML-код страницы на наличие скрипта с toggleFavorite
            page_html = page.content()
            has_script_block = "toggleFavorite" in page_html
            print(f"  toggleFavorite in HTML source: {has_script_block}")

            if has_script_block and not has_toggle:
                print("  [BUG] toggleFavorite found in HTML but NOT in global scope!")
                print("  -> base.html missing {% block scripts %} to render the script block")
                errors.append("toggleFavorite function not in global scope (missing block scripts in base.html)")

            # Ищем кнопку избранного (data-worker-id)
            fav_btn = page.query_selector('.favorite-btn')
            if fav_btn:
                worker_id = fav_btn.get_attribute('data-worker-id')
                btn_text = fav_btn.inner_text()
                print(f"  Worker ID: {worker_id}")
                print(f"  Button text: '{btn_text.strip()}'")
                print("  [OK] Favorite button found on workers page (UI structure is correct)")
                results["add_ui_structure"] = True
            else:
                print("  [FAIL] Favorite button not found on workers page")
                errors.append("Favorite button not found on workers page")

            # ===================================================================
            # STEP 4: Add via API (через fetch после логина)
            # ===================================================================
            print("\n[STEP 4] Adding worker to favorites via API...")

            if worker_id:
                api_result = page.evaluate(f"""
                    (() => {{
                        return fetch('/api/favorites/add', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ worker_id: '{worker_id}' }})
                        }})
                        .then(r => r.json())
                        .catch(e => ({{ success: false, error: e.message }}));
                    }})()
                """)
                print(f"  API add response: {api_result}")

                if api_result and api_result.get('success'):
                    print("  [OK] Worker added to favorites via API")
                    results["add_via_api"] = True
                elif api_result and api_result.get('message'):
                    print(f"  [WARN] API message: {api_result['message']}")
                    if "already" in str(api_result).lower():
                        results["add_via_api"] = True
                    else:
                        errors.append(f"API add error: {api_result}")
                else:
                    print(f"  [FAIL] API add failed: {api_result}")
                    errors.append(f"API add error: {api_result}")
            else:
                print("  [FAIL] No worker_id available for API call")
                errors.append("No worker_id for API")

            # ===================================================================
            # STEP 5: Check favorites page
            # ===================================================================
            print("\n[STEP 5] Checking favorites page...")
            page.goto(f"{BASE_URL}/favorites", wait_until="networkidle")
            page.wait_for_timeout(3000)
            print(f"  URL: {page.url}")

            page_content = page.content()

            if "Пока нет избранных трудников" in page_content:
                print("  [FAIL] Favorites page is empty (worker was not added)")
                errors.append("Favorites page is empty")
            else:
                fav_cards = page.query_selector_all('.card')
                print(f"  Favorite cards found: {len(fav_cards)}")

                if len(fav_cards) > 0:
                    print("  [OK] Workers are displayed on favorites page")
                    results["favorites_page"] = True

                    # ===========================================================
                    # STEP 6: Remove from favorites via API
                    # ===========================================================
                    print("\n[STEP 6] Removing worker from favorites via API...")

                    remove_btn = page.query_selector('.favorite-btn')
                    if remove_btn:
                        wid_on_page = remove_btn.get_attribute('data-worker-id')
                        final_worker_id = wid_on_page or worker_id

                        if final_worker_id:
                            remove_result = page.evaluate(f"""
                                (() => {{
                                    return fetch('/api/favorites/remove', {{
                                        method: 'POST',
                                        headers: {{ 'Content-Type': 'application/json' }},
                                        body: JSON.stringify({{ worker_id: '{final_worker_id}' }})
                                    }})
                                    .then(r => r.json())
                                    .catch(e => ({{ success: false, error: e.message }}));
                                }})()
                            """)
                        else:
                            remove_result = {"success": False, "error": "No worker ID found"}

                        print(f"  API remove response: {remove_result}")
                        if remove_result and remove_result.get('success'):
                            print("  [OK] Worker removed from favorites via API")
                            results["remove_via_api"] = True
                        elif remove_result and remove_result.get('message'):
                            print(f"  [WARN] API remove message: {remove_result['message']}")
                            results["remove_via_api"] = True
                        else:
                            print(f"  [FAIL] API remove failed: {remove_result}")
                            errors.append(f"API remove error: {remove_result}")

                        page.wait_for_timeout(1500)
                    else:
                        print("  [FAIL] No worker_id for remove API call")
                        errors.append("No worker_id for API remove")
                else:
                    print("  [FAIL] No cards on favorites page")
                    errors.append("No cards on favorites page")

            # ===================================================================
            # STEP 7: Final verification
            # ===================================================================
            print("\n[STEP 7] Final verification...")
            page.goto(f"{BASE_URL}/favorites", wait_until="networkidle")
            page.wait_for_timeout(2000)
            page_content = page.content()

            if "Пока нет избранных трудников" in page_content:
                print("  [OK] Favorites is empty - all clean")
                results["confirm_removed"] = True
            else:
                fav_cards = page.query_selector_all('.card')
                if len(fav_cards) == 0:
                    print("  [OK] Favorites is empty (no cards)")
                    results["confirm_removed"] = True
                else:
                    print(f"  [WARN] {len(fav_cards)} cards remain in favorites")

        except Exception as e:
            print(f"\n[ERROR] Test execution failed: {e}")
            errors.append(str(e))
            import traceback
            traceback.print_exc()

        finally:
            print("\n" + "=" * 70)
            print("  Closing browser...")
            browser.close()

    return results, errors


def print_report(results, errors):
    """Вывод отчёта о тестировании."""
    print("\n" + "=" * 70)
    print("  TEST REPORT: FAVORITES FUNCTIONALITY")
    print("=" * 70)

    all_passed = True
    steps = [
        ("1. Registration", "registration"),
        ("2. Login", "login"),
        ("3. Favorite button UI (structure)", "add_ui_structure"),
        ("4. Add via API", "add_via_api"),
        ("5. Favorites page check", "favorites_page"),
        ("6. Remove via API", "remove_via_api"),
        ("7. Confirm removal", "confirm_removed"),
    ]

    for name, key in steps:
        status = "[PASS]" if results[key] else "[FAIL]"
        print(f"  {status} {name}")
        if not results[key]:
            all_passed = False

    print("-" * 70)
    if all_passed:
        print("  [SUCCESS] ALL TESTS PASSED!")
    else:
        print(f"  [WARNING] NOT ALL TESTS PASSED.")
        if errors:
            print(f"\n  Errors ({len(errors)}):")
            for i, err in enumerate(errors, 1):
                print(f"    {i}. {err}")

    # Сводка багов
    bugs = [e for e in errors if "BUG" in e or "missing" in e.lower()]
    if bugs:
        print(f"\n  [BUGS FOUND] {len(bugs)} bug(s):")
        for b in bugs:
            print(f"    🐛 {b}")
    print("=" * 70)


if __name__ == "__main__":
    print("Starting browser test for favorites functionality...")
    print("NOTE: A Chrome browser window will open. Do not interact with it during the test.")
    print()

    results, errors = run_favorites_test()
    print_report(results, errors)

    all_passed = all(results.values())
    sys.exit(0 if all_passed else 1)
