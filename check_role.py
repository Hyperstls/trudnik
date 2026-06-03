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
    
    # Проверяем role в session
    role_data = page.evaluate("sessionStorage.getItem('role')")
    print(f"sessionStorage role: {role_data}")
    
    # Переход на my-jobs
    with page.expect_navigation():
        page.goto(BASE_URL + "/my-jobs")
    
    page.wait_for_timeout(3000)
    
    print(f"URL после my-jobs: {page.url}")
    
    # Проверяем HTML
    html = page.content()
    import re
    
    # Ищем flash сообщения
    flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', html)
    print("\nFlash messages:", flash_matches)
    
    # Ищем заголовок
    h1_match = re.search(r'<h1[^>]*>([^<]*)</h1>', html)
    if h1_match:
        print(f"H1: {h1_match.group(1)}")
    
    browser.close()
