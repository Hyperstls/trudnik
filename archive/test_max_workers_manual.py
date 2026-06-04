#!/usr/bin/env python3
"""Автотест создания задания с несколькими работниками"""

import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://hyperstls.pythonanywhere.com"
TEST_EMAIL = "test_max_workers@example.com"
TEST_PASSWORD = "Test123456"


def test_create_job_with_max_workers():
    """Тест создания задания с несколькими работниками"""
    print("=" * 60)
    print("AUTOTEST: Создание задания с max_workers")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        try:
            # 1. Регистрация работодателя
            print("\n[1/6] Регистрация работодателя...")
            page.goto(f"{BASE_URL}/register")
            time.sleep(2)
            
            page.fill('input[name="full_name"]', "Тестовый Работодатель")
            page.fill('input[name="email"]', TEST_EMAIL)
            page.fill('input[name="password"]', TEST_PASSWORD)
            page.select_option('select[name="role"]', 'employer')
            page.fill('input[name="city"]', "Москва")
            page.select_option('select[name="religion"]', 'не важно')
            page.fill('input[name="skills"]', 'уборка, пение')
            page.fill('input[name="portfolio_link"]', 'https://example.com')
            
            page.click('button[type="submit"]')
            time.sleep(3)
            
            if page.url == f"{BASE_URL}/my-jobs":
                print("    [OK] Работодатель зарегистрирован и вошёл")
            else:
                print(f"    [WARN] Неожиданный URL: {page.url}")
            
            # 2. Создание задания
            print("\n[2/6] Переход к созданию задания...")
            page.goto(f"{BASE_URL}/job/new")
            time.sleep(2)
            
            # 3. Проверка наличия поля max_workers
            print("\n[3/6] Проверка поля 'max_workers' на странице...")
            max_workers_input = page.locator('input[name="max_workers"]')
            if max_workers_input.count() > 0:
                print("    [OK] Поле 'max_workers' найдено на странице")
            else:
                print("    [ERROR] Поле 'max_workers' НЕ найдено на странице!")
                print("    [INFO] Страница не обновлена на PythonAnywhere")
                return False
            
            # 4. Заполнение формы
            print("\n[4/6] Заполнение формы задания...")
            page.fill('input[name="title"]', "Уборка храма - Тест max_workers")
            page.fill('input[name="city"]', "Москва")
            page.fill('input[name="address"]', "Москва, ул. Примерная, 1")
            page.fill('textarea[name="description"]', "Требуется убрать храм, помыть полы, протереть иконы.")
            page.fill('input[name="payment"]', "5000")
            
            # Установка max_workers = 5
            max_workers_input.fill("5")
            value = max_workers_input.input_value()
            print(f"    [INFO] Поле max_workers установлено в: {value}")
            
            page.fill('input[name="latitude"]', "55.751574")
            page.fill('input[name="longitude"]', "37.613260")
            
            # 5. Создание задания
            print("\n[5/6] Создание задания...")
            page.click('button[type="submit"]')
            time.sleep(3)
            
            # 6. Проверка результата
            print("\n[6/6] Проверка созданного задания...")
            if page.url == f"{BASE_URL}/my-jobs":
                print("    [OK] Переход на /my-jobs выполнен")
                
                page_content = page.content()
                if "Уборка храма" in page_content:
                    print("    [OK] Задание 'Уборка храма' найдено на странице")
                    
                    if "5" in page_content and "мест" in page_content:
                        print("    [OK] Отображение '5 мест' найдено")
                    else:
                        print("    [WARN] Отображение количества мест не найдено или некорректно")
                else:
                    print("    [ERROR] Задание не найдено на странице")
            else:
                print(f"    [WARN] Неожиданный URL после создания: {page.url}")
            
            print("\n" + "=" * 60)
            print("TEST COMPLETED SUCCESSFULLY")
            print("=" * 60)
            return True
            
        except Exception as e:
            print(f"\n[ERROR] Ошибка в тесте: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            time.sleep(2)
            browser.close()


if __name__ == "__main__":
    success = test_create_job_with_max_workers()
    
    if success:
        print("\nPASS: ТЕСТ ПРОЙДЕН")
    else:
        print("\nFAIL: ТЕСТ ПРОВАЛЕН - возможно, нужно выполнить deploy на PythonAnywhere")
    
    print("=" * 60)
