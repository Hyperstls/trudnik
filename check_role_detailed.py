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
    
    # Проверяем cookies
    cookies_before = page.context.cookies()
    print("\nCookies before my-jobs:")
    for cookie in cookies_before:
        if 'session' in cookie['name'].lower():
            print(f"  {cookie['name']}: {cookie['value'][:50]}...")
    
    # Переход на my-jobs
    with page.expect_navigation():
        page.goto(BASE_URL + "/my-jobs")
    
    page.wait_for_timeout(3000)
    
    print(f"\nURL после my-jobs: {page.url}")
    
    # Проверяем cookies
    cookies_after = page.context.cookies()
    print("\nCookies after my-jobs:")
    for cookie in cookies_after:
        if 'session' in cookie['name'].lower():
            print(f"  {cookie['name']}: {cookie['value'][:50]}...")
    
    # Проверяем, что в HTML
    html = page.content()
    import re
    
    # Ищем flash сообщения
    flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', html)
    print("\nFlash messages:", flash_matches)
    
    # Ищем "Доступ только для работодателей"
    if "Доступ только для работодателей" in html:
        print("Error: Доступ только для работодателей")
    
    browser.close()
