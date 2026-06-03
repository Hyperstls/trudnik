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
    
    page.fill("input[name='email']", "test_employer@test.com")
    page.fill("input[name='password']", "Test123456")
    
    page.click("button[type='submit']")
    page.wait_for_timeout(5000)
    
    html = page.content()
    
    # Ищем flash сообщения
    import re
    flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', html)
    print("Flash messages:", flash_matches)
    
    # Ищем сообщения об ошибке
    error_matches = re.findall(r'class=[\'"][^\'"]*error[^\'"]*[\'"][^>]*>([^<]*)', html, re.IGNORECASE)
    print("Error messages:", error_matches)
    
    # Ищем любые сообщения
    msg_matches = re.findall(r'<p[^>]*>([^<]*(?:ошибк|ошибка|неверн|не|[a-zA-Z]+)[^<]*)</p>', html, re.IGNORECASE)
    print("Message paragraphs:", msg_matches[:10])
    
    # Ищем все текстовые сообщения
    text_matches = re.findall(r'<div[^>]*class=[\'"][^\'"]*space-y-4[^\'"]*[\'"][^>]*>(.*?)</div>', html, re.DOTALL)
    for match in text_matches:
        print("Form content:", match[:200])
    
    browser.close()
