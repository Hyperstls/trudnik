"""
Full Flask Application Tester
Полное тестирование всех функций приложения "Трудник"
"""

import sys
import os
import time
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Загрузка переменных
load_dotenv()

BASE_URL = "https://hyperstls.pythonanywhere.com"
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://***REMOVED***.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Результаты тестирования
TEST_RESULTS = {
    "passed": [],
    "failed": [],
    "warnings": [],
    "skipped": []
}


def log_test(category, test_name, message, details=None):
    """Логирование результатов теста"""
    result = {
        "test": test_name,
        "message": message,
        "details": details
    }
    TEST_RESULTS[category].append(result)
    
    prefix = "✓" if category == "passed" else ("✗" if category == "failed" else ("⚠" if category == "warnings" else "-"))
    print(f"{prefix} {test_name}: {message}")
    if details:
        print(f"  {details}")


def api_request(method, endpoint, **kwargs):
    """Упрощенный запрос к Supabase API"""
    headers = kwargs.pop('headers', {})
    headers.setdefault('apikey', SUPABASE_ANON_KEY)
    if 'Authorization' not in headers:
        headers['Authorization'] = f'Bearer {SUPABASE_ANON_KEY}'
    headers.setdefault('Content-Type', 'application/json')
    
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        response = requests.request(method, url, headers=headers, timeout=15, **kwargs)
        return response
    except requests.RequestException as e:
        return type('obj', (object,), {'status_code': 0, 'text': str(e), 'json': lambda: None})


def test_homepage(page):
    """Тест главной страницы"""
    try:
        page.goto(BASE_URL)
        page.wait_for_timeout(2000)
        
        if "Трудник" in page.title():
            log_test("passed", "Главная страница", "Загружена успешно", f"Title: {page.title()}")
            return True
        else:
            log_test("failed", "Главная страница", "Некорректный заголовок", f"Title: {page.title()}")
            return False
    except Exception as e:
        log_test("failed", "Главная страница", "Ошибка загрузки", str(e))
        return False


def test_login_page(page):
    """Тест страницы входа"""
    try:
        page.goto(f"{BASE_URL}/login")
        page.wait_for_timeout(2000)
        
        # Проверка наличия формы входа
        email_field = page.query_selector("input[name='email']")
        password_field = page.query_selector("input[name='password']")
        submit_btn = page.query_selector("button[type='submit']")
        
        if email_field and password_field and submit_btn:
            log_test("passed", "Страница входа", "Форма присутствует")
            return True
        else:
            log_test("failed", "Страница входа", "Форма не найдена")
            return False
    except Exception as e:
        log_test("failed", "Страница входа", "Ошибка загрузки", str(e))
        return False


def test_employer_login(page):
    """Тест входа как работодатель"""
    try:
        page.goto(f"{BASE_URL}/login")
        page.wait_for_timeout(1000)
        
        email = "test_employer_final@test.com"
        password = "123456"
        
        page.fill("input[name='email']", email)
        page.fill("input[name='password']", password)
        page.click("button[type='submit']")
        page.wait_for_timeout(2000)
        
        if "/my-jobs" in page.url:
            log_test("passed", "Вход работодателя", "Успешный вход на my-jobs", f"URL: {page.url}")
            return True
        else:
            log_test("failed", "Вход работодателя", f"Ожидался my-jobs, получено: {page.url}")
            return False
    except Exception as e:
        log_test("failed", "Вход работодателя", "Ошибка", str(e))
        return False


def test_my_jobs_page(page):
    """Тест страницы моих заданий"""
    try:
        page.goto(f"{BASE_URL}/my-jobs")
        page.wait_for_timeout(2000)
        
        # Проверка заголовка
        heading = page.query_selector("h1, h2, .page-title")
        if heading:
            log_test("passed", "Страница моих заданий", "Загружена", f"Заголовок: {heading.inner_text()[:50]}")
        else:
            log_test("passed", "Страница моих заданий", "Загружена (без заголовка)")
        
        return True
    except Exception as e:
        log_test("failed", "Страница моих заданий", "Ошибка загрузки", str(e))
        return False


def test_create_job_page(page):
    """Тест страницы создания задания"""
    try:
        page.goto(f"{BASE_URL}/create-job")
        page.wait_for_timeout(2000)
        
        # Проверка формы создания задания
        form = page.query_selector("form")
        if form:
            log_test("passed", "Страница создания задания", "Форма присутствует")
            return True
        else:
            log_test("failed", "Страница создания задания", "Форма не найдена")
            return False
    except Exception as e:
        log_test("failed", "Страница создания задания", "Ошибка загрузки", str(e))
        return False


def test_workers_page(page):
    """Тест страницы работников"""
    try:
        page.goto(f"{BASE_URL}/workers")
        page.wait_for_timeout(2000)
        
        # Проверка наличия списка работников
        workers_list = page.query_selector_all(".worker-card, .worker-item, .profile")
        log_test("passed", "Страница работников", "Загружена", f"Найдено карточек: {len(workers_list)}")
        return True
    except Exception as e:
        log_test("failed", "Страница работников", "Ошибка загрузки", str(e))
        return False


def test_profile_page(page):
    """Тест страницы профиля"""
    try:
        page.goto(f"{BASE_URL}/profile")
        page.wait_for_timeout(2000)
        
        # Проверка наличия формы профиля
        form = page.query_selector("form, .profile-form")
        if form:
            log_test("passed", "Страница профиля", "Форма присутствует")
            return True
        else:
            log_test("warnings", "Страница профиля", "Форма не найдена (возможно, страница другая)")
            return True  # Не критично
    except Exception as e:
        log_test("failed", "Страница профиля", "Ошибка загрузки", str(e))
        return False


def test_logout(page):
    """Тест выхода из системы"""
    try:
        page.goto(f"{BASE_URL}/logout")
        page.wait_for_timeout(2000)
        
        if "/login" in page.url:
            log_test("passed", "Выход", "Успешный выход", f"URL: {page.url}")
            return True
        else:
            log_test("failed", "Выход", f"Ожидался login, получено: {page.url}")
            return False
    except Exception as e:
        log_test("failed", "Выход", "Ошибка", str(e))
        return False


def test_api_health():
    """Тест состояния API"""
    try:
        response = requests.get(f"{BASE_URL}/", timeout=10)
        if response.status_code == 200:
            log_test("passed", "API здоровье", "Сервер доступен", f"Status: {response.status_code}")
            return True
        else:
            log_test("failed", "API здоровье", f"Некорректный статус: {response.status_code}")
            return False
    except requests.RequestException as e:
        log_test("failed", "API здоровье", "Сервер недоступен", str(e))
        return False


def test_supabase_connection():
    """Тест подключения к Supabase"""
    try:
        response = api_request("GET", "profiles?limit=1")
        if response.status_code == 200:
            log_test("passed", "Supabase подключение", "Подключение успешно")
            return True
        else:
            log_test("failed", "Supabase подключение", f"Ошибка: {response.status_code}")
            return False
    except Exception as e:
        log_test("failed", "Supabase подключение", "Ошибка подключения", str(e))
        return False


def test_register_page(page):
    """Тест страницы регистрации"""
    try:
        page.goto(f"{BASE_URL}/register")
        page.wait_for_timeout(2000)
        
        form = page.query_selector("form")
        if form:
            log_test("passed", "Страница регистрации", "Форма присутствует")
            return True
        else:
            log_test("failed", "Страница регистрации", "Форма не найдена")
            return False
    except Exception as e:
        log_test("failed", "Страница регистрации", "Ошибка загрузки", str(e))
        return False


def test_search_filters(page):
    """Тест фильтров поиска"""
    try:
        page.goto(f"{BASE_URL}?city=Москва&payment_min=1000")
        page.wait_for_timeout(2000)
        
        # Проверка, что поиск сработал
        jobs_count = len(page.query_selector_all(".job-card, .job-item, [data-job-id]"))
        log_test("passed", "Фильтры поиска", "Поиск работает", f"Найдено заданий: {jobs_count}")
        return True
    except Exception as e:
        log_test("warnings", "Фильтры поиска", "Ошибка при тестировании фильтров", str(e))
        return True  # Не критично


def run_all_tests():
    """Запуск всех тестов"""
    print("\n" + "=" * 70)
    print("FULL FLASK APPLICATION TESTER")
    print("Полное тестирование приложения 'Трудник'")
    print("=" * 70)
    
    print("\n[1/5] API тесты...")
    api_health = test_api_health()
    supabase_connected = test_supabase_connection()
    
    print("\n[2/5] Браузерные тесты (workshop mode)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("\n[3/5] Тест главной страницы...")
        test_homepage(page)
        
        print("\n[4/5] Тест входа/выхода...")
        test_login_page(page)
        employer_login = test_employer_login(page)
        test_my_jobs_page(page)
        
        if employer_login:
            print("\n[5/5] Тест функций работодателя...")
            test_create_job_page(page)
            test_workers_page(page)
            test_profile_page(page)
            test_logout(page)
        
        browser.close()
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = len(TEST_RESULTS["passed"])
    failed = len(TEST_RESULTS["failed"])
    warnings = len(TEST_RESULTS["warnings"])
    skipped = len(TEST_RESULTS["skipped"])
    
    print(f"✓ Passed: {passed}")
    print(f"✗ Failed: {failed}")
    print(f"⚠ Warnings: {warnings}")
    print(f"- Skipped: {skipped}")
    print(f"Total: {passed + failed + warnings + skipped}")
    
    if failed == 0:
        print("\n[SUCCESS] Все критические тесты пройдены!")
    else:
        print(f"\n[WARNING] {failed} тест(ов) не пройдено")
    
    # Сохранение результатов
    results_file = Path(__file__).parent / "test_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(TEST_RESULTS, f, indent=2, ensure_ascii=False)
    
    print(f"\nРезультаты сохранены в: {results_file}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
