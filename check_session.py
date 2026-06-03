import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Вход
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "new_employer4@test.com")
    page.fill("input[name='password']", "Test123456")
    
    # Ожидаем навигацию
    with page.expect_navigation():
        page.click("button[type='submit']")
    
    page.wait_for_timeout(3000)
    
    print(f"URL после входа: {page.url}")
    
    # Сохраняем куки
    cookies_before = page.context.cookies()
    print("\nCookies before my-jobs:")
    for cookie in cookies_before:
        if 'session' in cookie['name'].lower():
            print(f"  {cookie['name']}: {cookie['value'][:50]}...")
    
    # Перейти на my-jobs
    with page.expect_navigation():
        page.goto(BASE_URL + "/my-jobs")
    
    page.wait_for_timeout(3000)
    
    print(f"URL после my-jobs: {page.url}")
    
    # Проверяем куки после
    cookies_after = page.context.cookies()
    print("\nCookies after my-jobs:")
    for cookie in cookies_after:
        if 'session' in cookie['name'].lower():
            print(f"  {cookie['name']}: {cookie['value'][:50]}...")
    
    # Проверяем HTML
    html = page.content()
    import re
    if "my-jobs" in html.lower() or "мои задания" in html.lower():
        print("\nMy-jobs content found!")
    else:
        print("\nMy-jobs content NOT found")
        # Показываем первую часть HTML
        print("HTML (first 500 chars):", html[:500])
    
    browser.close()
