import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Перехватываем все запросы
    def handle_request(request):
        print(f"Request: {request.method} {request.url}")
    
    def handle_response(response):
        print(f"Response: {response.status} {response.url}")
    
    page.on("request", handle_request)
    page.on("response", handle_response)
    
    # Вход
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "new_employer4@test.com")
    page.fill("input[name='password']", "Test123456")
    
    # Ожидаем навигацию
    with page.expect_navigation():
        page.click("button[type='submit']")
    
    page.wait_for_timeout(3000)
    
    print(f"\n=== После входа ===")
    print(f"URL: {page.url}")
    
    # Переход на my-jobs
    print("\n=== Переход на my-jobs ===")
    with page.expect_navigation():
        page.goto(BASE_URL + "/my-jobs")
    
    page.wait_for_timeout(3000)
    
    print(f"URL после my-jobs: {page.url}")
    
    browser.close()
