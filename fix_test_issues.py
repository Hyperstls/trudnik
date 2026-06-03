"""
Fix create job and workers page issues
"""

import sys
import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://hyperstls.pythonanywhere.com"

def fix_create_job():
    """Попытка исправить создание задания"""
    print("\n" + "="*60)
    print("FIX: Create Job Functionality")
    print("="*60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Вход
        page.goto(f"{BASE_URL}/login")
        page.wait_for_timeout(2000)
        page.fill("input[name='email']", "test_employer_final@test.com")
        page.fill("input[name='password']", "123456")
        page.click("button[type='submit']")
        page.wait_for_timeout(2000)
        
        print(f"Current URL: {page.url}")
        
        # Создание задания
        page.goto(f"{BASE_URL}/create-job")
        page.wait_for_timeout(2000)
        
        # Заполнение только видимых полей
        print("\nFill visible fields...")
        page.fill("input[name='organization_name']", "Test Organization")
        page.fill("textarea[name='org_description']", "Organization description")
        page.fill("textarea[name='object_description']", "Object description")
        page.fill("input[name='work_type']", "Work type test")
        page.fill("textarea[name='detailed_description']", "Detailed description")
        
        # Время и дата
        page.fill("input[name='date']", "2026-06-15")
        page.fill("input[name='time']", "10:00")
        page.fill("input[name='payment']", "5000")
        page.fill("input[name='city']", "Moscow")
        
        # Предпочтительное вероисповедание
        page.select_option("select[name='preferred_religion']", "не важно")
        
        print("\nClick publish button...")
        # Клик по кнопке публикации
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)
        
        print(f"URL after publish: {page.url}")
        print(f"Title: {page.title()}")
        
        # Проверка сообщения об успехе
        content = page.content()
        if "Job published" in content or "Задание опубликовано" in content or "/my-jobs" in page.url:
            print("\n[SUCCESS] Job created successfully!")
        else:
            print(f"\n[FAIL] Job creation failed")
            print(f"Content preview: {content[:500]}")
        
        # Сохраняем скриншот
        page.screenshot(path="create_job_fixed.png")
        print("\nScreenshot saved to: create_job_fixed.png")
        
        browser.close()

def fix_workers_page():
    """Диагностика страницы workers"""
    print("\n" + "="*60)
    print("FIX: Workers Page Diagnosis")
    print("="*60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Тест 1: Загрузка без входа
        print("\nTest 1: Load /workers without login...")
        try:
            page.goto(f"{BASE_URL}/workers", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            print(f"URL: {page.url}")
            print(f"Title: {page.title()}")
            print(f"Content contains 'Трудники': {'Трудники' in page.content()}")
            
            workers = page.query_selector_all(".worker-card")
            print(f"Worker cards found: {len(workers)}")
            
            # Сохраняем скриншот
            page.screenshot(path="workers_diagnosis_1.png")
            print("Screenshot saved to: workers_diagnosis_1.png")
            
        except Exception as e:
            print(f"Error: {e}")
        
        # Тест 2: Загрузка после входа работника
        print("\nTest 2: Load /workers after worker login...")
        
        # Вход как работник
        page.goto(f"{BASE_URL}/login")
        page.wait_for_timeout(1000)
        page.fill("input[name='email']", "test_worker_2026@test.com")
        page.fill("input[name='password']", "123456")
        page.click("button[type='submit']")
        page.wait_for_timeout(2000)
        
        print(f"URL after login: {page.url}")
        
        # Переход к workers
        try:
            page.goto(f"{BASE_URL}/workers", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            print(f"URL after workers: {page.url}")
            print(f"Title: {page.title()}")
            
            workers = page.query_selector_all(".worker-card")
            print(f"Worker cards found: {len(workers)}")
            
            # Сохраняем скриншот
            page.screenshot(path="workers_diagnosis_2.png")
            print("Screenshot saved to: workers_diagnosis_2.png")
            
        except Exception as e:
            print(f"Error: {e}")
            page.screenshot(path="workers_diagnosis_error.png")
            print("Error screenshot saved to: workers_diagnosis_error.png")
        
        browser.close()

if __name__ == "__main__":
    fix_create_job()
    time.sleep(2)
    fix_workers_page()
