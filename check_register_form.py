import sys
import io
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "https://hyperstls.pythonanywhere.com"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    
    # Перейти на регистрацию
    page.goto(BASE_URL + "/register")
    page.wait_for_timeout(3000)
    
    print("URL:", page.url)
    
    # Ищем все поля ввода
    inputs = page.query_selector_all("input")
    print(f"\nFound {len(inputs)} input(s)")
    
    for i, inp in enumerate(inputs):
        input_type = inp.get_attribute("type") or "text"
        name = inp.get_attribute("name") or "(no name)"
        placeholder = inp.get_attribute("placeholder") or "(no placeholder)"
        id_attr = inp.get_attribute("id") or "(no id)"
        print(f"Input {i+1}: type={input_type}, name={name}, placeholder={placeholder}, id={id_attr}")
    
    # Ищем select
    selects = page.query_selector_all("select")
    print(f"\nFound {len(selects)} select(s)")
    
    for i, sel in enumerate(selects):
        name = sel.get_attribute("name") or "(no name)"
        id_attr = sel.get_attribute("id") or "(no id)"
        print(f"Select {i+1}: name={name}, id={id_attr}")
    
    # Ищем кнопки
    buttons = page.query_selector_all("button")
    print(f"\nFound {len(buttons)} button(s)")
    
    for i, btn in enumerate(buttons):
        btn_text = btn.inner_text().strip() if btn.inner_text() else "(empty)"
        btn_type = btn.get_attribute("type") or "button"
        print(f"Button {i+1}: type={btn_type}, text={btn_text}")
    
    browser.close()
