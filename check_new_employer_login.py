import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Перехватываем запросы и ответы
    def handle_response(response):
        if response.request.method == "POST" and "/login" in response.url:
            print(f"POST response status: {response.status}")
            print(f"POST response URL: {response.url}")
    
    page.on("response", handle_response)
    
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "new_employer4@test.com")
    page.fill("input[name='password']", "Test123456")
    
    # Нажимаем кнопку
    page.click("button[type='submit']")
    page.wait_for_timeout(5000)
    
    print(f"\nURL после входа: {page.url}")
    
    # Проверяем куки
    cookies = page.context.cookies()
    print("\nCookies:")
    for cookie in cookies:
        print(f"  {cookie['name']}: {cookie['value'][:50]}...")
    
    # Получаем HTML
    html = page.content()
    
    # Ищем flash сообщения
    import re
    error_matches = re.findall(r'class=[\'"][^\'"]*error[^\'"]*[\'"][^>]*>([^<]*)', html, re.IGNORECASE)
    print("\nError messages:", error_matches)
    
    browser.close()
