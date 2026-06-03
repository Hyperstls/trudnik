"""Create job using direct API call from browser"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from playwright.sync_api import sync_playwright
import json

BASE_URL = "https://hyperstls.pythonanywhere.com"
SUPABASE_URL = "https://***REMOVED***.supabase.co"
SUPABASE_ANON_KEY = "***REMOVED***"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.set_default_timeout(60000)
    
    # Вход
    print("1. Logging in...")
    page.goto(f"{BASE_URL}/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "test_employer_final@test.com")
    page.fill("input[name='password']", "123456")
    page.click("button[type='submit']")
    page.wait_for_timeout(2000)
    
    print(f"2. Current URL: {page.url}")
    
    # Получение user_id из сессии
    print("3. Getting user_id from session...")
    user_id = page.evaluate("() => localStorage.getItem('user_id')")
    if not user_id:
        # Попытка получить из cookie или другого места
        user_id = "c6291021-7741-4a10-b68c-b1c7ec002442"
    print(f"User ID: {user_id}")
    
    # Создание задания через API напрямую
    print("4. Creating job via direct API call...")
    
    job_data = {
        'employer_id': user_id,
        'organization_name': 'Test Direct API',
        'org_description': 'Direct API test description',
        'object_description': 'Object description via API',
        'work_type': 'Direct API test work',
        'detailed_description': 'Detailed description via API',
        'date_time': '2026-06-17T10:00:00',
        'payment_amount': 7000,
        'address': 'Moscow',
        'city': 'Moscow',
        'lat': 55.75,
        'lng': 37.61,
        'preferred_religion': 'не важно',
    }
    
    # Выполняем запрос напрямую из браузера
    page.evaluate(f"""
        const headers = {{
            'apikey': '{SUPABASE_ANON_KEY}',
            'Authorization': 'Bearer {SUPABASE_ANON_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }};
        
        fetch('{SUPABASE_URL}/rest/v1/jobs', {{
            method: 'POST',
            headers: headers,
            body: JSON.stringify({json.dumps(job_data)})
        }})
        .then(response => response.json())
        .then(data => {{
            console.log('Success:', data);
            alert('Job created: ' + JSON.stringify(data));
        }})
        .catch(error => {{
            console.error('Error:', error);
            alert('Error: ' + error);
        }});
    """)
    
    page.wait_for_timeout(3000)
    
    # Переход к my-jobs
    print("5. Navigating to my-jobs...")
    page.goto(f"{BASE_URL}/my-jobs")
    page.wait_for_timeout(2000)
    
    print(f"6. URL: {page.url}")
    print(f"7. Title: {page.title()}")
    
    # Проверка создания задания
    content = page.content()
    if "Test Direct API" in content:
        print("\n[SUCCESS] Job found in my-jobs!")
    else:
        print("\n[INFO] Checking if job was created...")
        print(f"Content preview: {content[:500]}")
    
    page.screenshot(path="create_job_api.png")
    print("\nScreenshot saved to: create_job_api.png")
    
    browser.close()
