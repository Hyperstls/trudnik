import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Вход
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "new_employer4@test.com")
    page.fill("input[name='password']", "Test123456")
    page.click("button[type='submit']")
    page.wait_for_timeout(5000)
    
    print(f"URL после входа: {page.url}")
    
    # Перейти на my-jobs
    page.goto(BASE_URL + "/my-jobs")
    page.wait_for_timeout(5000)
    
    print(f"URL после my-jobs: {page.url}")
    
    # Получить HTML и искатьflash сообщения
    html = page.content()
    
    # Ищем flash сообщения
    import re
    flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', html)
    print("\nFlash messages:", flash_matches)
    
    # Ищем формы создания задания
    job_form = re.search(r'<form[^>]*create-job[^>]*>(.*?)</form>', html, re.DOTALL)
    if job_form:
        print("\nCreate job form found!")
        print(job_form.group(1)[:500])
    else:
        print("\nCreate job form not found")
        # Попробуем найти любую форму
        forms = re.findall(r'<form[^>]*>.*?</form>', html, re.DOTALL)
        print(f"\nFound {len(forms)} form(s)")
        for i, form in enumerate(forms):
            print(f"Form {i+1} (first 300 chars):", form[:300])
    
    browser.close()
