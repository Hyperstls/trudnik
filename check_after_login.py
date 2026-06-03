import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Вход как работодатель
    page.goto(BASE_URL + "/login")
    page.wait_for_timeout(2000)
    
    page.fill("input[name='email']", "test_employer@test.com")
    page.fill("input[name='password']", "Test123456")
    page.click("button[type='submit']")
    page.wait_for_timeout(3000)
    
    print("URL после входа:", page.url)
    
    # Ищем все ссылки
    links = page.query_selector_all("a")
    print(f"\nFound {len(links)} link(s)")
    
    for i, link in enumerate(links[:15]):
        href = link.get_attribute("href") or "(no href)"
        text = link.inner_text().strip() if link.inner_text() else "(empty)"
        if href and href != "(no href)":
            print(f"Link {i+1}: href={href}, text={text[:50]}")
    
    # Ищем кнопки
    buttons = page.query_selector_all("button")
    print(f"\nFound {len(buttons)} button(s)")
    
    for i, btn in enumerate(buttons[:10]):
        btn_text = btn.inner_text().strip() if btn.inner_text() else "(empty)"
        print(f"Button {i+1}: text={btn_text}")
    
    browser.close()
