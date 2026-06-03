import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(5000)
    
    html = page.content()
    
    # Ищем email поле
    print("Checking for input[name='email']...")
    email_input = page.query_selector("input[name='email']")
    if email_input:
        print("Email input found!")
        print("Email HTML:", email_input.inner_html()[:200])
    else:
        print("Email input NOT found")
    
    # Попробуем селектор по placeholder
    print("\nChecking for placeholder 'Email'...")
    email_by_placeholder = page.query_selector("input[placeholder='Email']")
    if email_by_placeholder:
        print("Found by placeholder!")
    else:
        print("NOT found by placeholder")
    
    browser.close()
