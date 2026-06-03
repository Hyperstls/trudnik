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
    
    # Ищем任何形式
    import re
    form_matches = re.findall(r'<form[^>]*>.*?</form>', html, re.DOTALL)
    print(f"Found {len(form_matches)} form(s)")
    
    for i, form in enumerate(form_matches):
        print(f"\n--- Form {i+1} ---")
        print(form[:1000])
    
    browser.close()
