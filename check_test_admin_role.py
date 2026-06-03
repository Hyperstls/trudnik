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
    
    page.fill("input[name='email']", "test_admin@test.com")
    page.fill("input[name='password']", "Test123456")
    
    # Ожидаем навигацию
    with page.expect_navigation():
        page.click("button[type='submit']")
    
    page.wait_for_timeout(3000)
    
    print(f"URL после входа: {page.url}")
    
    # Проверяем flash сообщения
    html = page.content()
    import re
    flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', html)
    print(f"Flash messages: {flash_matches}")
    
    # Переход на my-jobs
    with page.expect_navigation():
        page.goto(BASE_URL + "/my-jobs")
    
    page.wait_for_timeout(3000)
    
    print(f"URL после my-jobs: {page.url}")
    
    # Проверяем flash сообщения
    html = page.content()
    flash_matches = re.findall(r'class=[\'"][^\'"]*flash[^\'"]*[\'"][^>]*>([^<]*)', html)
    print(f"Flash messages after my-jobs: {flash_matches}")
    
    # Ищем "Доступ только для работодателей"
    if "Доступ только для работодателей" in html:
        print("ERROR: Доступ только для работодателей")
    
    browser.close()
