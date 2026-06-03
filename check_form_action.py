import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    html = page.content()
    
    # Ищем форму и её action
    import re
    form_match = re.search(r'<form[^>]*action=[\'"]([^\'"]*)[\'"][^>]*>(.*?)</form>', html, re.DOTALL)
    if form_match:
        print("Form action:", form_match.group(1))
        print("Form HTML:", form_match.group(2)[:500])
    else:
        print("Form not found")
    
    # Ищем скрипты
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    print(f"\nFound {len(scripts)} script(s)")
    for i, script in enumerate(scripts[:5]):
        print(f"Script {i+1} (first 200 chars):", script[:200])
    
    browser.close()
