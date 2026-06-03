import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(3000)
    
    # Выполняем JavaScript для получения полей
    email = page.evaluate("document.querySelector(\"input[name='email']\").value")
    password = page.evaluate("document.querySelector(\"input[name='password']\").value")
    
    print(f"Email value: '{email}'")
    print(f"Password value: '{password}'")
    
    # Заполняем
    page.evaluate("""
        document.querySelector(\"input[name='email']\").value = 'test_employer@test.com';
        document.querySelector(\"input[name='password']\").value = 'Test123456';
    """)
    
    # Проверяем после заполнения
    email = page.evaluate("document.querySelector(\"input[name='email']\").value")
    password = page.evaluate("document.querySelector(\"input[name='password']\").value")
    
    print(f"\nAfter fill - Email: '{email}'")
    print(f"After fill - Password: '{password}'")
    
    # Нажимаем кнопку через JS
    page.evaluate("document.querySelector(\"button[type='submit']\").click()")
    page.wait_for_timeout(5000)
    
    print(f"\nURL after click: {page.url}")
    
    # Проверяем куки
    cookies = page.evaluate("document.cookie")
    print(f"document.cookie: {cookies}")
    
    browser.close()
