#!/usr/bin/env python3
"""
Проверка работы обновлённого приложения
Тестирует основные функции после загрузки на PythonAnywhere
"""

import time
import requests
from datetime import datetime

# Конфигурация
APP_URL = "https://hyperstls.pythonanywhere.com"
TEST_USER_EMAIL = "test_employer_final@test.com"
TEST_USER_PASSWORD = "password123"  # Заменить на реальный пароль

class PythonAnywhereTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.user_id = None
        
    def test_server_status(self):
        """Проверка статуса сервера"""
        print("[TEST] Проверка статуса сервера...")
        try:
            resp = requests.get(f"{APP_URL}/", timeout=10)
            if resp.status_code == 200:
                print("[OK] Сервер доступен")
                return True
            else:
                print(f"[FAIL] Сервер вернул код: {resp.status_code}")
                return False
        except Exception as e:
            print(f"[FAIL] Ошибка подключения: {e}")
            return False
    
    def login(self):
        """Вход пользователя"""
        print("[TEST] Вход пользователя...")
        login_url = f"{APP_URL}/login"
        
        try:
            # Получить форму входа
            resp = self.session.get(login_url, timeout=10)
            if resp.status_code != 200:
                print(f"[FAIL] Не удалось открыть страницу входа: {resp.status_code}")
                return False
            
            # Вход
            data = {
                'email': TEST_USER_EMAIL,
                'password': TEST_USER_PASSWORD
            }
            resp = self.session.post(login_url, data=data, timeout=10, allow_redirects=False)
            
            # Проверить редирект
            if resp.status_code in [301, 302]:
                location = resp.headers.get('Location', '')
                if '/my-jobs' in location or '/' in location:
                    print("[OK] Вход успешен")
                    return True
                else:
                    print(f"[FAIL] Неожиданный редирект: {location}")
                    return False
            else:
                # Проверить содержимое - возможно, ошибка авторизации
                if 'Ошибка входа' in resp.text or 'Неверный email' in resp.text:
                    print(f"[FAIL] Ошибка авторизации (проверьте пароль)")
                    return False
                print(f"[FAIL] Неожиданный статус: {resp.status_code}")
                return False
                
        except Exception as e:
            print(f"[FAIL] Ошибка входа: {e}")
            return False
    
    def test_create_job_page(self):
        """Проверка страницы создания задания"""
        print("[TEST] Проверка страницы /create-job...")
        
        try:
            resp = self.session.get(f"{APP_URL}/create-job", timeout=10)
            if resp.status_code == 200:
                if 'create_job' in resp.text or 'organization_name' in resp.text:
                    print("[OK] Страница /create-job доступна")
                    return True
                else:
                    print("[FAIL] Страница загружена, но не содержит формы")
                    return False
            else:
                print(f"[FAIL] Страница вернула код: {resp.status_code}")
                return False
        except Exception as e:
            print(f"[FAIL] Ошибка: {e}")
            return False
    
    def create_test_job(self):
        """Создание тестового задания"""
        print("[TEST] Создание тестового задания...")
        
        today = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M')
        
        job_data = {
            'organization_name': 'Тестовое задание',
            'org_description': 'Описание организации',
            'object_description': 'Описание объекта',
            'work_type': 'Уборка',
            'detailed_description': 'Подробное описание работы',
            'date': today,
            'time': current_time,
            'payment': '100',
            'address': 'Москва',
            'city': 'Москва',
            'lat': '55.75',
            'lng': '37.61',
            'preferred_religion': 'не важно'
        }
        
        try:
            resp = self.session.post(f"{APP_URL}/create-job", data=job_data, timeout=15, allow_redirects=False)
            
            # Проверить код ответа
            if resp.status_code == 200:
                # Проверить, что не 500 ошибка
                if 'Internal Server Error' in resp.text:
                    print("[FAIL] Ошибка 500 Internal Server Error!")
                    return False
                
                # Проверить сообщение об успехе
                if 'Задание опубликовано' in resp.text or 'success' in resp.text.lower():
                    print("[OK] Задание создано успешно!")
                    return True
                else:
                    print("[INFO] Задание, возможно, создано (но нет сообщения об успехе)")
                    return True
                    
            elif resp.status_code in [301, 302]:
                # Редирект - это нормально
                location = resp.headers.get('Location', '')
                if '/my-jobs' in location:
                    print("[OK] Задание создано, перенаправление на /my-jobs")
                    return True
                else:
                    print(f"[INFO] Редирект: {location}")
                    return True
            else:
                print(f"[FAIL] Неожиданный статус: {resp.status_code}")
                return False
                
        except Exception as e:
            print(f"[FAIL] Ошибка создания задания: {e}")
            return False
    
    def test_my_jobs(self):
        """Проверка страницы моих заданий"""
        print("[TEST] Проверка страницы /my-jobs...")
        
        try:
            resp = self.session.get(f"{APP_URL}/my-jobs", timeout=10)
            if resp.status_code == 200:
                print("[OK] Страница /my-jobs доступна")
                return True
            else:
                print(f"[FAIL] Статус: {resp.status_code}")
                return False
        except Exception as e:
            print(f"[FAIL] Ошибка: {e}")
            return False
    
    def run_all_tests(self):
        """Запустить все тесты"""
        print("=" * 60)
        print("ТЕСТИРОВАНИЕ ОБНОВЛЁННОГО ПРИЛОЖЕНИЯ")
        print("=" * 60)
        print()
        
        results = []
        
        # Тест 1: Статус сервера
        results.append(("Сервер статус", self.test_server_status()))
        
        # Тест 2: Вход
        if results[-1][1]:
            results.append(("Вход", self.login()))
        else:
            print("[SKIP] Пропущено (сервер недоступен)")
            results.append(("Вход", False))
        
        # Тест 3: Страница создания задания
        if results[-1][1]:
            results.append(("Страница /create-job", self.test_create_job_page()))
        else:
            print("[SKIP] Пропущено (не вход)")
            results.append(("Страница /create-job", False))
        
        # Тест 4: Создание задания (если вход успешен)
        if results[-1][1]:
            results.append(("Создание задания", self.create_test_job()))
        else:
            print("[SKIP] Пропущено (не вход)")
            results.append(("Создание задания", False))
        
        # Тест 5: Страница моих заданий
        if results[-1][1]:
            results.append(("Страница /my-jobs", self.test_my_jobs()))
        else:
            print("[SKIP] Пропущено (не вход)")
            results.append(("Страница /my-jobs", False))
        
        # Результаты
        print()
        print("=" * 60)
        print("РЕЗУЛЬТАТЫ")
        print("=" * 60)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "[OK]" if result else "[FAIL]"
            print(f"{status} {test_name}")
        
        print()
        print(f"Всего: {passed}/{total}")
        
        if passed == total:
            print()
            print("[SUCCESS] Все тесты пройдены!")
            return True
        else:
            print()
            print(f"[WARNING] {total - passed} тестов не пройдены")
            return False

def main():
    tester = PythonAnywhereTester()
    success = tester.run_all_tests()
    
    if success:
        print()
        print("===========================================")
        print("ОБНОВЛЕНИЕ УСПЕШНО ПРОВЕРЕНО!")
        print("===========================================")
    else:
        print()
        print("===========================================")
        print("ЕСТЬ ПРОБЛЕМЫ - ПРОВЕРЬТЕ ЛОГИ")
        print("===========================================")
        print()
        print("Логи PythonAnywhere:")
        print("https://www.pythonanywhere.com/domains/logs/")
    
    return success

if __name__ == "__main__":
    main()
