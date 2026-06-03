"""Test form submission for create-job"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from playwright.sync_api import sync_playwright

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_default_timeout(60000)
    
    # Вход
    print("1. Navigating to login...")
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
    
    # Используем JavaScript для заполнения скрытых полей
    page.evaluate("""
        document.querySelector("input[name='organization_name']").value = 'Test Organization JS';
        document.querySelector("textarea[name='org_description']").value = 'Organization description JS';
        document.querySelector("textarea[name='object_description']").value = 'Object description JS';
        document.querySelector("input[name='work_type']").value = 'Work type JS';
        document.querySelector("textarea[name='detailed_description']").value = 'Detailed description JS';
        document.querySelector("input[name='date']").value = '2026-06-16';
        document.querySelector("input[name='time']").value = '14:00';
        document.querySelector("input[name='payment']").value = '6000';
        document.querySelector("input[name='city']").value = 'Moscow';
        document.querySelector("input[name='lat']").value = '55.75';
        document.querySelector("input[name='lng']").value = '37.61';
        document.querySelector("input[name='address']").value = 'Moscow, Russia';
        document.querySelector("select[name='preferred_religion']").value = 'не важно';
    """)
    
    # Проверка заполненных полей
    print("5. Checking filled values...")
    org_name = page.evaluate("document.querySelector('input[name=\"organization_name\"]').value")
    lat = page.evaluate("document.querySelector('input[name=\"lat\"]').value")
    lng = page.evaluate("document.querySelector('input[name=\"lng\"]').value")
    print(f"   org_name: {org_name}")
    print(f"   lat: {lat}")
    print(f"   lng: {lng}")
    
    # Клик по кнопке
    print("6. Clicking publish button...")
    page.click("button[type='submit']")
    page.wait_for_timeout(3000)
    
    print(f"7. URL after publish: {page.url}")
    print(f"8. Title: {page.title()}")
    
    content = page.content()
    
    if "/my-jobs" in page.url:
        print("\n[SUCCESS] Job created successfully!")
    elif "500" in content or "Internal Server Error" in content:
        print("\n[FAIL] 500 Internal Server Error")
    else:
        print(f"\n[INFO] Content: {content[:500]}")
    
    page.screenshot(path="create_job_js.png")
    print("\nScreenshot saved to: create_job_js.png")
    
    browser.close()
