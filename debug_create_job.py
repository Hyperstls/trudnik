"""Debug Flask app logs for create-job"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from playwright.sync_api import sync_playwright
import json

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_default_timeout(60000)
    
    # Перехват network requests
    print("Setting up network monitoring...")
    
    def handle_request(route, request):
        print(f"[REQUEST] {request.method} {request.url}")
        if request.method == "POST" and "jobs" in request.url:
            print(f"[POST] Job creation attempt detected!")
            print(f"[POST] Headers: {request.headers}")
            if request.post_data:
                print(f"[POST] Data: {request.post_data[:500]}")
        route.continue_()
    
    def handle_response(route, response):
        request_url = response.request.url
        status = response.status
        print(f"[RESPONSE] {request_url} -> {status}")
        
        if status >= 400:
            print(f"[ERROR] Non-2xx response!")
        
    page.route("**/*", handle_request)
    
    # Вход
    print("\n1. Logging in...")
    page.goto(f"{BASE_URL}/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "test_employer_final@test.com")
    page.fill("input[name='password']", "123456")
    page.click("button[type='submit']")
    page.wait_for_timeout(2000)
    
    print(f"2. Current URL: {page.url}")
    
    # Создание задания
    print("3. Navigating to create-job...")
    page.goto(f"{BASE_URL}/create-job")
    page.wait_for_timeout(2000)
    
    # Заполнение формы
    print("4. Filling form...")
    page.evaluate("""
        document.querySelector("input[name='organization_name']").value = 'Test JS';
        document.querySelector("input[name='lat']").value = '55.75';
        document.querySelector("input[name='lng']").value = '37.61';
    """)
    
    # Перехват запроса к /jobs
    jobs_response = None
    
    def handle_response(route, response):
        nonlocal jobs_response
        request_url = response.request.url
        if "jobs" in request_url and response.request.method == "POST":
            jobs_response = {
                "status": response.status,
                "url": request_url,
                "response": None
            }
            print(f"\n[JOB RESPONSE] Status: {response.status}")
        route.continue_()
    
    page.route("**/rest/v1/jobs*", handle_response)
    
    # Клик по кнопке
    print("5. Clicking publish button...")
    try:
        page.click("button[type='submit']")
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"Click error: {e}")
    
    print(f"6. URL after: {page.url}")
    print(f"7. Title: {page.title()}")
    
    page.screenshot(path="create_job_debug.png")
    print("\nScreenshot saved to: create_job_debug.png")
    
    browser.close()
