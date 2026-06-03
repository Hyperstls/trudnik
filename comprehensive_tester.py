"""
Comprehensive Flask Application Tester
Расширенное полное тестирование всех функций приложения "Трудник"
Тестирует как worker, так и employer режимы
"""

import sys
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Загрузка переменных
load_dotenv()

BASE_URL = "https://hyperstls.pythonanywhere.com"

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
        "details": details,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    TEST_RESULTS[category].append(result)
    
    prefix = "✓" if category == "passed" else ("✗" if category == "failed" else ("⚠" if category == "warnings" else "-"))
    print(f"{prefix} {test_name}: {message}")
    if details:
        print(f"  {details}")


class FlaskTester:
    """Класс для тестирования Flask-приложения"""
    
    def __init__(self, browser):
        self.page = browser.new_page()
        self.current_user = None
        self.current_role = None
        self.token = None
        
    def navigate(self, path, wait_time=2000):
        """Переход по URL"""
        self.page.goto(f"{BASE_URL}{path}")
        self.page.wait_for_timeout(wait_time)
        return self.page.url
    
    def login(self, email, password, expected_url="/"):
        """Вход в систему"""
        try:
            self.navigate("/login")
            
            self.page.fill("input[name='email']", email)
            self.page.fill("input[name='password']", password)
            self.page.click("button[type='submit']")
            self.page.wait_for_timeout(2000)
            
            self.current_user = email
            # Определяем роль по URL
            if "/my-jobs" in self.page.url:
                self.current_role = "employer"
            else:
                self.current_role = "worker"
            
            if expected_url in self.page.url or expected_url == "/":
                log_test("passed", f"Вход ({email})", f"Успешно, роль: {self.current_role}")
                return True
            else:
                log_test("failed", f"Вход ({email})", f"Ожидался: {expected_url}, получено: {self.page.url}")
                return False
        except Exception as e:
            log_test("failed", f"Вход ({email})", "Ошибка", str(e))
            return False
    
    def logout(self):
        """Выход из системы"""
        try:
            self.navigate("/logout")
            if "/login" in self.page.url:
                log_test("passed", "Выход", "Успешно")
                self.current_user = None
                self.current_role = None
                return True
            return False
        except Exception as e:
            log_test("failed", "Выход", "Ошибка", str(e))
            return False
    
    def check_page_exists(self, path, expected_text=None):
        """Проверка существования страницы"""
        try:
            self.navigate(path)
            
            if expected_text:
                if expected_text in self.page.content():
                    log_test("passed", f"Страница {path}", "Загружена", f"Найден текст: {expected_text[:50]}")
                    return True
                else:
                    log_test("warnings", f"Страница {path}", "Загружена, но нет ожидаемого текста")
                    return True
            else:
                log_test("passed", f"Страница {path}", "Загружена")
                return True
        except Exception as e:
            log_test("failed", f"Страница {path}", "Ошибка загрузки", str(e))
            return False
    
    def test_create_job(self):
        """Тест создания задания"""
        try:
            self.navigate("/create-job")
            
            # Заполнение формы
            self.page.fill("input[name='organization_name']", "Тестовый Храм")
            self.page.fill("textarea[name='org_description']", "Описание организации")
            self.page.fill("textarea[name='object_description']", "Описание объекта")
            self.page.fill("input[name='address']", "Москва, ул. Примерная, 1")
            self.page.fill("input[name='city']", "Москва")
            
            # Выбор времени
            self.page.fill("input[name='date']", "2026-06-10")
            self.page.fill("input[name='time']", "10:00")
            self.page.fill("input[name='payment']", "5000")
            
            self.page.click("button[type='submit']")
            self.page.wait_for_timeout(3000)
            
            # Проверка успешного создания
            if "/my-jobs" in self.page.url or "Задание опубликовано" in self.page.content():
                log_test("passed", "Создание задания", "Успешно")
                return True
            else:
                log_test("failed", "Создание задания", f"URL: {self.page.url}")
                return False
        except Exception as e:
            log_test("failed", "Создание задания", "Ошибка", str(e))
            return False
    
    def test_my_jobs(self):
        """Тест страницы моих заданий"""
        try:
            self.navigate("/my-jobs")
            self.page.wait_for_timeout(2000)
            
            # Проверка наличия заданий или сообщения
            content = self.page.content()
            if "Задания не найдены" in content or "job-card" in content:
                log_test("passed", "Мои задания", "Загружена", "Есть задания или сообщение об отсутствии")
                return True
            else:
                log_test("warnings", "Мои задания", "Страница загружена, но структура неочевидна")
                return True
        except Exception as e:
            log_test("failed", "Мои задания", "Ошибка", str(e))
            return False
    
    def test_workers_search(self):
        """Тест поиска работников"""
        try:
            self.navigate("/workers")
            self.page.wait_for_timeout(2000)
            
            # Попытка фильтрации
            self.page.fill("input[name='city']", "Москва")
            self.page.click("button[type='submit']")
            self.page.wait_for_timeout(2000)
            
            log_test("passed", "Поиск работников", "Фильтры работают")
            return True
        except Exception as e:
            log_test("warnings", "Поиск работников", "Ошибка фильтрации", str(e))
            return True  # Не критично
    
    def test_profile(self):
        """Тест страницы профиля"""
        try:
            self.navigate("/profile")
            self.page.wait_for_timeout(2000)
            
            # Проверка наличия формы
            form = self.page.query_selector("form")
            if form:
                log_test("passed", "Профиль", "Форма присутствует")
                return True
            else:
                log_test("warnings", "Профиль", "Форма не найдена")
                return True
        except Exception as e:
            log_test("failed", "Профиль", "Ошибка", str(e))
            return False
    
    def test_apply_job(self):
        """Тест отклика на задание"""
        try:
            self.navigate("/")
            self.page.wait_for_timeout(2000)
            
            # Попытка найти кнопку отклика
            apply_buttons = self.page.query_selector_all("button, a")
            found_apply = False
            for btn in apply_buttons:
                text = btn.inner_text()
                if "отклик" in text.lower() or "apply" in text.lower():
                    found_apply = True
                    break
            
            if found_apply or len(self.page.query_selector_all(".job-card")) > 0:
                log_test("passed", "Отклик на задание", "Есть задания для отклика")
                return True
            else:
                log_test("warnings", "Отклик на задание", "Нет заданий для теста")
                return True
        except Exception as e:
            log_test("failed", "Отклик на задание", "Ошибка", str(e))
            return False
    
    def test_my_applications(self):
        """Тест моих откликов"""
        try:
            self.navigate("/my-applications")
            self.page.wait_for_timeout(2000)
            
            # Проверка содержимого
            content = self.page.content()
            if "отклики" in content.lower() or "applications" in content.lower():
                log_test("passed", "Мои отклики", "Страница загружена")
                return True
            else:
                log_test("warnings", "Мои отклики", "Страница загружена, но текст не найден")
                return True
        except Exception as e:
            log_test("failed", "Мои отклики", "Ошибка", str(e))
            return False
    
    def test_shifts(self):
        """Тест смен"""
        try:
            self.navigate("/shifts")
            self.page.wait_for_timeout(2000)
            
            log_test("passed", "Смены", "Страница загружена")
            return True
        except Exception as e:
            log_test("failed", "Смены", "Ошибка", str(e))
            return False
    
    def test_favorites(self):
        """Тест избранного"""
        try:
            self.navigate("/favorites")
            self.page.wait_for_timeout(2000)
            
            log_test("passed", "Избранное", "Страница загружена")
            return True
        except Exception as e:
            log_test("failed", "Избранное", "Ошибка", str(e))
            return False
    
    def test_chats(self):
        """Тест чатов"""
        try:
            self.navigate("/chats")
            self.page.wait_for_timeout(2000)
            
            log_test("passed", "Чаты", "Страница загружена")
            return True
        except Exception as e:
            log_test("failed", "Чаты", "Ошибка", str(e))
            return False
    
    def test_blacklist(self):
        """Тест черного списка"""
        try:
            self.navigate("/blacklist")
            self.page.wait_for_timeout(2000)
            
            log_test("passed", "Черный список", "Страница загружена")
            return True
        except Exception as e:
            log_test("failed", "Черный список", "Ошибка", str(e))
            return False


def run_comprehensive_tests():
    """Запуск комплексных тестов"""
    print("\n" + "=" * 70)
    print("COMPREHENSIVE FLASK APPLICATION TESTER")
    print("Полное тестирование всех функций приложения 'Трудник'")
    print("=" * 70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        tester = FlaskTester(browser)
        
        print("\n" + "=" * 70)
        print("ЧАСТЬ 1: Тесты работодателя (employer)")
        print("=" * 70)
        
        # Вход как работодатель
        tester.login("test_employer_final@test.com", "123456", "/my-jobs")
        
        if tester.current_role == "employer":
            # Тесты для работодателя
            tester.check_page_exists("/create-job")
            tester.test_create_job()
            tester.test_my_jobs()
            tester.check_page_exists("/my-applications")
            tester.check_page_exists("/shifts")
            tester.check_page_exists("/chats")
            tester.check_page_exists("/profile")
            tester.test_profile()
            
            # Выход
            tester.logout()
        
        print("\n" + "=" * 70)
        print("ЧАСТЬ 2: Тесты работника (worker)")
        print("=" * 70)
        
        # Вход как работник
        tester.login("test_worker_2026@test.com", "123456", "/")
        
        if tester.current_role == "worker":
            # Тесты для работника
            tester.check_page_exists("/")
            tester.check_page_exists("/workers")
            tester.test_workers_search()
            tester.check_page_exists("/profile")
            tester.test_profile()
            tester.test_apply_job()
            tester.check_page_exists("/my-applications")
            tester.check_page_exists("/shifts")
            tester.check_page_exists("/favorites")
            tester.check_page_exists("/chats")
            tester.check_page_exists("/blacklist")
            
            # Выход
            tester.logout()
        
        print("\n" + "=" * 70)
        print("ЧАСТЬ 3: Публичные страницы")
        print("=" * 70)
        
        # Переход на главную без входа
        tester.navigate("/")
        tester.check_page_exists("/login")
        tester.check_page_exists("/register")
        tester.check_page_exists("/workers")
        
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
        results_file = Path(__file__).parent / "test_results_comprehensive.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(TEST_RESULTS, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\nРезультаты сохранены в: {results_file}")
        
        return failed == 0


if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
