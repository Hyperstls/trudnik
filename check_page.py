import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(BASE_URL)
    page.wait_for_timeout(3000)
    
    print("URL:", page.url)
    print("\n--- HTML (first 2000 chars) ---")
    html = page.content()
    print(html[:2000])
    
    # Попытка найти ссылку на регистрацию
    try:
        register_link = page.query_selector_all("a")
        print("\n--- All links found ---")
        for link in register_link:
            href = link.get_attribute("href")
            text = link.inner_text().strip() if link.inner_text() else ""
            if href:
                print(f"  href={href}, text={text}")
    except Exception as e:
        print("Error:", e)
    
    browser.close()
