import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Вход как работодатель
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    print("Форма до заполнения:")
    print("Email:", page.input_value("input[name='email']"))
    
    page.fill("input[name='email']", "test_employer@test.com")
    page.fill("input[name='password']", "Test123456")
    
    print("\nФорма после заполнения:")
    print("Email:", page.input_value("input[name='email']"))
    print("Password:", page.input_value("input[name='password']"))
    
    # Отправка формы
    page.click("button[type='submit']")
    page.wait_for_timeout(5000)
    
    print("\nURL после отправки:", page.url)
    
    # Проверяем сессию
    cookies = page.context.cookies()
    print("\nCookies:")
    for cookie in cookies:
        if 'session' in cookie['name'].lower():
            print(f"  {cookie['name']}: {cookie['value'][:50]}...")
    
    browser.close()
