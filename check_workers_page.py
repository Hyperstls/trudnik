"""
Check workers page functionality
"""

import sys
import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://hyperstls.pythonanywhere.com"

def test_workers_page():
    """Тест страницы работников"""
    print(f"\nTesting: {BASE_URL}/workers")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Увеличиваем таймаут
        page.set_default_timeout(60000)
        
        try:
            page.goto(f"{BASE_URL}/workers", wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            print(f"Current URL: {page.url}")
            
            # Проверка заголовка
            title = page.title()
            print(f"Page title: {title}")
            
            # Проверка наличия контента
            content = page.content()
            if "Трудники" in content:
                print("SUCCESS: Page contains expected content")
            else:
                print("WARNING: Page loaded but content might be missing")
            
            # Проверка карточек работников
            workers = page.query_selector_all(".worker-card")
            print(f"Found {len(workers)} worker cards")
            
            # Попытка фильтрации
            print("\nTrying filters...")
            try:
                page.fill("input[name='city']", "Moscow")
                page.wait_for_timeout(1000)
                print("Filter filled")
            except Exception as e:
                print(f"Filter error: {e}")
            
            # Ждем и сохраняем скриншот
            page.wait_for_timeout(3000)
            screenshot_path = "workers_page.png"
            page.screenshot(path=screenshot_path)
            print(f"\nScreenshot saved to: {screenshot_path}")
            
        except Exception as e:
            print(f"ERROR: {e}")
            # Сохраняем скриншот при ошибке
            try:
                page.screenshot(path="workers_error.png")
                print("Error screenshot saved to: workers_error.png")
            except:
                pass
        finally:
            browser.close()

if __name__ == "__main__":
    test_workers_page()
