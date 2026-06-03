import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    page.goto(BASE_URL)
    page.wait_for_timeout(3000)
    
    html = page.content()
    
    # Ищем ссылки на login/register
    import re
    login_matches = re.findall(r'href=[\'"](/[^\'"]*)[\'"]', html)
    print("All links found:")
    for link in set(login_matches):
        print(f"  {link}")
    
    # Ищем кнопки с текстом вход
    btn_pattern = r'<button[^>]*>([^<]*)</button>'
    btn_matches = re.findall(btn_pattern, html)
    print("\nAll buttons:")
    for btn in btn_matches[:10]:
        if btn.strip():
            print(f"  {btn.strip()[:50]}")
    
    browser.close()
