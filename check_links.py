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
    
    # Ищем любые ссылки на вход/регистрацию
    import re
    login_matches = re.findall(r'href=[\'"]([^\'"]*login[^\'"]*)[\'"]', html, re.IGNORECASE)
    register_matches = re.findall(r'href=[\'"]([^\'"]*register[^\'"]*)[\'"]', html, re.IGNORECASE)
    
    print("Login links:", login_matches)
    print("Register links:", register_matches)
    
    # Ищем кнопки с текстом вход/регистрация
    btn_pattern = r'<[^>]*>([^<]*вход|[^<]*войти|[^<]*входа|[^<]*регистраци|[^<]*зарегистри)[^<]*</'
    btn_matches = re.findall(btn_pattern, html, re.IGNORECASE)
    print("Buttons with login/reg text:", btn_matches)
    
    browser.close()
