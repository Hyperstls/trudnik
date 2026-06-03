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
    
    # Выполняем JS для проверки session в браузере
    session_data = page.evaluate("sessionStorage.getItem('session')")
    print(f"sessionStorage: {session_data}")
    
    # Проверяем cookies
    cookies = page.context.cookies()
    session_cookie = None
    for cookie in cookies:
        if 'session' in cookie['name'].lower():
            session_cookie = cookie['value']
            break
    
    print(f"session cookie: {session_cookie[:50]}...")
    
    # Попробуем обратиться к /profile для проверки данных
    page.goto(BASE_URL + "/profile")
    page.wait_for_timeout(3000)
    
    print(f"URL после /profile: {page.url}")
    
    html = page.content()
    import re
    # Ищем полное имя пользователя
    name_match = re.search(r'full_name.*?([А-Яа-яЁё]+ [А-Яа-яЁё]+)', html)
    if name_match:
        print(f"Found name: {name_match.group(1)}")
    
    browser.close()
