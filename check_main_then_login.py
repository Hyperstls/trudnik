import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Сначала на главную
    page.goto(BASE_URL)
    page.wait_for_timeout(2000)
    print("On main page")
    print("HTML (first 1000 chars):", page.content()[:1000])
    
    # Потом на login
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    print("\n\nOn login page")
    print("HTML (first 1000 chars):", page.content()[:1000])
    
    # Ищем email поле
    email_input = page.query_selector("input[name='email']")
    if email_input:
        print("\nEmail input found!")
    else:
        print("\nEmail input NOT found")
    
    browser.close()
