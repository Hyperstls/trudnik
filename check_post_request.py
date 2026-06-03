import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Перехватываем запросы
    def handle_request(route, request):
        if request.method == "POST":
            print(f"POST request to: {request.url}")
            print(f"POST data: {request.post_data}")
        route.continue_()
    
    page.route("**/*", handle_request)
    
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "test_employer@test.com")
    page.fill("input[name='password']", "Test123456")
    
    # Нажимаем кнопку
    page.click("button[type='submit']")
    page.wait_for_timeout(5000)
    
    print("URL после отправки:", page.url)
    
    browser.close()
