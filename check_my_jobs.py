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
    
    # Вход
    page.fill("input[name='email']", "new_employer4@test.com")
    page.fill("input[name='password']", "Test123456")
    page.click("button[type='submit']")
    page.wait_for_timeout(5000)
    
    print(f"URL после входа: {page.url}")
    
    # Переход на my-jobs
    page.goto(BASE_URL + "/my-jobs")
    page.wait_for_timeout(3000)
    
    print(f"URL после перехода на my-jobs: {page.url}")
    
    # Ищем все ссылки
    links = page.query_selector_all("a")
    print(f"\nFound {len(links)} link(s)")
    
    for i, link in enumerate(links[:20]):
        href = link.get_attribute("href") or "(no href)"
        text = link.inner_text().strip() if link.inner_text() else "(empty)"
        if href and href != "(no href)":
            print(f"Link {i+1}: href={href}, text={text[:50]}")
    
    browser.close()
